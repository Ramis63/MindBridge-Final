import http.server
import json
import logging
import os
import queue
import socketserver
import sqlite3
import hashlib
import uuid
import time

from server.auth import create_token, verify_token, extract_bearer_token, hash_password, verify_password
from server.config import DB_PATH, PORT, CORS_ORIGIN, ENV, DEBUG, validate_config
from server.events import publish, subscribe, unsubscribe
from server.fhir import (
    logs_to_bundle,
    log_to_observations,
    log_to_questionnaire_response,
    patient_reference,
    validate_fhir_bundle,
    validate_fhir_patient,
)
from server.validation import (
    ValidationError,
    validate_email,
    validate_log_entry,
    validate_name,
    validate_password,
    validate_settings,
)

DIRECTORY = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S',
)
logger = logging.getLogger('mindbridge')


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            user_email TEXT NOT NULL,
            date TEXT NOT NULL,
            mood INTEGER NOT NULL,
            energy INTEGER NOT NULL,
            sleep_hours REAL NOT NULL,
            sleep_quality TEXT NOT NULL,
            stress INTEGER NOT NULL,
            notes TEXT,
            tags TEXT,
            PRIMARY KEY (user_email, date)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            user_email TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
    logger.info('database_initialized path=%s env=%s', DB_PATH, ENV)


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_log(row) -> dict:
    return {
        'date': row['date'],
        'mood': row['mood'],
        'energy': row['energy'],
        'sleepHours': row['sleep_hours'],
        'sleepQuality': row['sleep_quality'],
        'stress': row['stress'],
        'notes': row['notes'],
        'tags': json.loads(row['tags']) if row['tags'] else [],
    }


def fetch_user_logs(user_email: str) -> list:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT * FROM logs WHERE user_email = ? ORDER BY date DESC',
        (user_email,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [row_to_log(row) for row in rows]


class DevelopmentHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def log_message(self, format, *args):
        logger.info('%s - %s', self.address_string(), format % args)

    def _cors_origin(self):
        origin = self.headers.get('Origin', '')
        if CORS_ORIGIN == '*':
            return '*'
        if origin and origin == CORS_ORIGIN:
            return origin
        return CORS_ORIGIN or '*'

    def _send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', self._cors_origin())
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header(
            'Access-Control-Allow-Headers',
            'Content-Type, Authorization, X-User-Email',
        )

    def end_headers(self):
        if not self.path.startswith('/api/'):
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self._send_cors_headers()
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def _read_json_body(self) -> dict:
        content_length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(content_length) if content_length else b'{}'
        return json.loads(raw.decode('utf-8'))

    def send_json_response(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def _require_auth(self) -> dict | None:
        token = extract_bearer_token(self.headers.get('Authorization'))
        if not token:
            legacy_email = self.headers.get('X-User-Email')
            if legacy_email:
                logger.warning('deprecated_auth_header email=%s', legacy_email.strip().lower())
                return {'sub': legacy_email.strip().lower()}
            self.send_json_response(401, {'error': 'Missing or invalid Authorization bearer token'})
            return None
        payload = verify_token(token)
        if not payload:
            self.send_json_response(401, {'error': 'Token expired or invalid'})
            return None
        return payload

    def do_GET(self):
        if self.path == '/api/logs':
            self.handle_get_logs()
        elif self.path == '/api/settings':
            self.handle_get_settings()
        elif self.path == '/api/fhir/Bundle':
            self.handle_get_fhir_bundle()
        elif self.path == '/api/fhir/Patient':
            self.handle_get_fhir_patient()
        elif self.path == '/api/events':
            self.handle_sse_stream()
        elif self.path == '/api/health':
            self.send_json_response(200, {'status': 'ok', 'env': ENV})
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == '/api/create-profile':
            self.handle_auth_signup()
        elif self.path == '/api/session':
            self.handle_auth_login()
        elif self.path == '/api/logs':
            self.handle_post_log()
        elif self.path == '/api/settings':
            self.handle_post_settings()
        else:
            self.send_json_response(404, {'error': 'API endpoint not found'})

    def handle_auth_signup(self):
        try:
            body = self._read_json_body()
            email = validate_email(body.get('email', ''))
            password = validate_password(body.get('password', ''))
            fname = validate_name(body.get('firstName', ''), 'firstName')
            lname = validate_name(body.get('lastName', ''), 'lastName')

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT email FROM users WHERE email = ?', (email,))
            if cursor.fetchone():
                conn.close()
                self.send_json_response(409, {'error': 'Email is already registered'})
                return

            pw_hash = hash_password(password)
            cursor.execute(
                'INSERT INTO users (email, first_name, last_name, password_hash) VALUES (?, ?, ?, ?)',
                (email, fname, lname, pw_hash),
            )
            conn.commit()
            conn.close()

            token = create_token(email, fname, lname)
            logger.info('user_registered email=%s', email)
            self.send_json_response(200, {
                'user': {'email': email, 'firstName': fname, 'lastName': lname},
                'token': token,
            })
        except ValidationError as exc:
            logger.warning('signup_validation_failed field=%s msg=%s', exc.field, exc.message)
            self.send_json_response(400, {'error': exc.message, 'field': exc.field})
        except Exception as exc:
            logger.exception('signup_failed')
            self.send_json_response(500, {'error': 'Internal server error' if not DEBUG else str(exc)})

    def handle_auth_login(self):
        try:
            body = self._read_json_body()
            email = validate_email(body.get('email', ''))
            password = validate_password(body.get('password', ''))

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
            user_row = cursor.fetchone()
            conn.close()

            if not user_row or not verify_password(password, user_row['password_hash']):
                logger.warning('login_failed email=%s', email)
                self.send_json_response(401, {'error': 'Invalid email or password'})
                return

            token = create_token(
                user_row['email'],
                user_row['first_name'],
                user_row['last_name'],
            )
            logger.info('login_success email=%s', email)
            self.send_json_response(200, {
                'user': {
                    'email': user_row['email'],
                    'firstName': user_row['first_name'],
                    'lastName': user_row['last_name'],
                },
                'token': token,
            })
        except ValidationError as exc:
            self.send_json_response(400, {'error': exc.message, 'field': exc.field})
        except Exception as exc:
            logger.exception('login_failed')
            self.send_json_response(500, {'error': 'Internal server error' if not DEBUG else str(exc)})

    def handle_get_logs(self):
        payload = self._require_auth()
        if not payload:
            return
        try:
            user_email = payload['sub']
            logs = fetch_user_logs(user_email)
            self.send_json_response(200, logs)
        except Exception as exc:
            logger.exception('get_logs_failed')
            self.send_json_response(500, {'error': 'Internal server error' if not DEBUG else str(exc)})

    def handle_get_fhir_bundle(self):
        payload = self._require_auth()
        if not payload:
            return
        try:
            user_email = payload['sub']
            logs = fetch_user_logs(user_email)
            bundle = logs_to_bundle(user_email, logs)
            validate_fhir_bundle(bundle)
            self.send_json_response(200, bundle)
        except Exception as exc:
            logger.exception('fhir_bundle_failed')
            self.send_json_response(500, {'error': 'Internal server error' if not DEBUG else str(exc)})

    def handle_get_fhir_patient(self):
        payload = self._require_auth()
        if not payload:
            return
        try:
            patient = patient_reference(payload['sub'])
            validate_fhir_patient(patient)
            self.send_json_response(200, patient)
        except Exception as exc:
            logger.exception('fhir_patient_failed')
            self.send_json_response(500, {'error': 'Internal server error' if not DEBUG else str(exc)})

    def handle_get_settings(self):
        payload = self._require_auth()
        if not payload:
            return
        try:
            user_email = payload['sub']
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM settings WHERE user_email = ?', (user_email,))
            row = cursor.fetchone()
            conn.close()
            settings = json.loads(row['value']) if row else {'theme': 'light', 'anonymousSharing': False}
            self.send_json_response(200, settings)
        except Exception as exc:
            logger.exception('get_settings_failed')
            self.send_json_response(500, {'error': 'Internal server error' if not DEBUG else str(exc)})

    def handle_post_log(self):
        payload = self._require_auth()
        if not payload:
            return
        try:
            user_email = payload['sub']
            entry = validate_log_entry(self._read_json_body())

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT OR REPLACE INTO logs
                (user_email, date, mood, energy, sleep_hours, sleep_quality, stress, notes, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    user_email,
                    entry['date'],
                    entry['mood'],
                    entry['energy'],
                    entry['sleepHours'],
                    entry['sleepQuality'],
                    entry['stress'],
                    entry['notes'],
                    json.dumps(entry['tags']),
                ),
            )
            conn.commit()
            conn.close()

            observations = log_to_observations(user_email, entry)
            questionnaire = log_to_questionnaire_response(user_email, entry)
            publish(user_email, 'log_saved', {
                'log': entry,
                'fhir': {
                    'observations': observations,
                    'questionnaireResponse': questionnaire,
                },
            })
            logger.info('log_saved email=%s date=%s', user_email, entry['date'])
            self.send_json_response(200, {
                'success': True,
                'message': 'Log saved successfully',
                'fhir': {
                    'observations': observations,
                    'questionnaireResponse': questionnaire,
                },
            })
        except ValidationError as exc:
            logger.warning('log_validation_failed field=%s msg=%s', exc.field, exc.message)
            self.send_json_response(400, {'error': exc.message, 'field': exc.field})
        except Exception as exc:
            logger.exception('post_log_failed')
            self.send_json_response(500, {'error': 'Internal server error' if not DEBUG else str(exc)})

    def handle_post_settings(self):
        payload = self._require_auth()
        if not payload:
            return
        try:
            user_email = payload['sub']
            settings = validate_settings(self._read_json_body())

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT OR REPLACE INTO settings (user_email, value) VALUES (?, ?)',
                (user_email, json.dumps(settings)),
            )
            conn.commit()
            conn.close()
            logger.info('settings_saved email=%s', user_email)
            self.send_json_response(200, {'success': True, 'message': 'Settings saved successfully'})
        except ValidationError as exc:
            self.send_json_response(400, {'error': exc.message, 'field': exc.field})
        except Exception as exc:
            logger.exception('post_settings_failed')
            self.send_json_response(500, {'error': 'Internal server error' if not DEBUG else str(exc)})

    def handle_sse_stream(self):
        payload = self._require_auth()
        if not payload:
            return
        user_email = payload['sub']
        q = subscribe(user_email)
        logger.info('sse_subscribed email=%s', user_email)

        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self._send_cors_headers()
        self.end_headers()

        try:
            self.wfile.write(b': connected\n\n')
            self.wfile.flush()
            while True:
                try:
                    message = q.get(timeout=25)
                    self.wfile.write(f'data: {message}\n\n'.encode('utf-8'))
                    self.wfile.flush()
                except queue.Empty:
                    self.wfile.write(b': heartbeat\n\n')
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            logger.info('sse_disconnected email=%s', user_email)
        finally:
            unsubscribe(user_email, q)


if __name__ == '__main__':
    validate_config()
    init_db()
    os.chdir(DIRECTORY)
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(('', PORT), DevelopmentHTTPRequestHandler) as httpd:
        logger.info('server_started port=%s env=%s db=%s', PORT, ENV, DB_PATH)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info('server_stopped')
            httpd.server_close()
