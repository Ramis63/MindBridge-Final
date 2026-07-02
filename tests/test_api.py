import json
import os
import tempfile
import unittest
from http.client import HTTPConnection
from threading import Thread

import run
from server import config
from server.auth import create_token, verify_token
from server.fhir import log_to_observations, logs_to_bundle, patient_reference, validate_fhir_bundle, validate_fhir_patient
from server.validation import ValidationError, validate_log_entry, validate_settings


class AuthTests(unittest.TestCase):
    def test_token_roundtrip(self):
        token = create_token('student@uni.de', 'Ada', 'Lovelace')
        payload = verify_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload['sub'], 'student@uni.de')
        self.assertEqual(payload['firstName'], 'Ada')

    def test_invalid_token_rejected(self):
        self.assertIsNone(verify_token('not.a.valid.token'))


class ValidationTests(unittest.TestCase):
    def test_valid_log(self):
        entry = validate_log_entry({
            'date': '2026-07-02',
            'mood': 4,
            'energy': 3,
            'stress': 2,
            'sleepHours': 7.5,
            'sleepQuality': 'Good',
            'notes': 'Exam week',
            'tags': ['#Exam'],
        })
        self.assertEqual(entry['mood'], 4)

    def test_stress_out_of_range(self):
        with self.assertRaises(ValidationError):
            validate_log_entry({
                'date': '2026-07-02',
                'mood': 4,
                'energy': 3,
                'stress': 9,
                'sleepHours': 7,
                'sleepQuality': 'Good',
            })


class FhirTests(unittest.TestCase):
    def test_observations_use_fhir_structure(self):
        log = {
            'date': '2026-07-02',
            'mood': 4,
            'energy': 3,
            'stress': 2,
            'sleepHours': 7,
            'sleepQuality': 'Good',
            'notes': '',
            'tags': [],
        }
        observations = log_to_observations('student@uni.de', log)
        self.assertEqual(len(observations), 5)
        self.assertEqual(observations[0]['resourceType'], 'Observation')
        self.assertEqual(observations[0]['code']['coding'][0]['system'], 'http://loinc.org')

    def test_bundle_type(self):
        bundle = logs_to_bundle('student@uni.de', [{
            'date': '2026-07-02',
            'mood': 4,
            'energy': 3,
            'stress': 2,
            'sleepHours': 7,
            'sleepQuality': 'Good',
            'notes': '',
            'tags': [],
        }])
        self.assertEqual(bundle['resourceType'], 'Bundle')
        self.assertEqual(bundle['type'], 'collection')
        self.assertGreater(len(bundle['entry']), 0)


class ApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmp.name, 'test.db')
        config.DB_PATH = cls.db_path
        run.DB_PATH = cls.db_path
        run.init_db()

        cls.httpd = run.socketserver.ThreadingTCPServer(('127.0.0.1', 0), run.DevelopmentHTTPRequestHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def _request(self, method, path, body=None, token=None):
        conn = HTTPConnection('127.0.0.1', self.port, timeout=5)
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        payload = json.dumps(body).encode() if body is not None else None
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        data = response.read().decode()
        conn.close()
        return response.status, json.loads(data) if data else {}

    def test_signup_login_and_fhir_bundle(self):
        status, signup = self._request('POST', '/api/create-profile', {
            'firstName': 'Test',
            'lastName': 'User',
            'email': 'test@uni.de',
            'password': 'secret12',
        })
        self.assertEqual(status, 200)
        self.assertIn('token', signup)

        status, login = self._request('POST', '/api/session', {
            'email': 'test@uni.de',
            'password': 'secret12',
        })
        self.assertEqual(status, 200)
        token = login['token']

        status, save = self._request('POST', '/api/logs', {
            'date': '2026-07-02',
            'mood': 4,
            'energy': 3,
            'stress': 2,
            'sleepHours': 7,
            'sleepQuality': 'Good',
            'notes': 'Integration test',
            'tags': ['#Exam'],
        }, token=token)
        self.assertEqual(status, 200)
        self.assertIn('fhir', save)

        status, bundle = self._request('GET', '/api/fhir/Bundle', token=token)
        self.assertEqual(status, 200)
        self.assertEqual(bundle['resourceType'], 'Bundle')

    def test_unauthorized_without_token(self):
        status, _ = self._request('GET', '/api/logs')
        self.assertEqual(status, 401)

    def test_invalid_log_rejected(self):
        _, signup = self._request('POST', '/api/create-profile', {
            'firstName': 'Bad',
            'lastName': 'Log',
            'email': 'bad@uni.de',
            'password': 'secret12',
        })
        token = signup['token']
        status, body = self._request('POST', '/api/logs', {
            'date': '2026-07-02',
            'mood': 99,
            'energy': 3,
            'stress': 2,
            'sleepHours': 7,
            'sleepQuality': 'Good',
        }, token=token)
        self.assertEqual(status, 400)
        self.assertIn('error', body)


class AdditionalValidationTests(unittest.TestCase):
    def test_validate_settings_accepts_valid_theme_and_anonymous_sharing(self):
        settings = validate_settings({'theme': 'dark', 'anonymousSharing': True})
        self.assertEqual(settings['theme'], 'dark')
        self.assertTrue(settings['anonymousSharing'])

    def test_validate_settings_rejects_invalid_theme(self):
        with self.assertRaises(ValidationError):
            validate_settings({'theme': 'blue', 'anonymousSharing': False})


class FhirValidationTests(unittest.TestCase):
    def test_fhir_bundle_validation(self):
        bundle = logs_to_bundle('student@uni.de', [{
            'date': '2026-07-02',
            'mood': 4,
            'energy': 3,
            'stress': 2,
            'sleepHours': 7,
            'sleepQuality': 'Good',
            'notes': '',
            'tags': [],
        }])
        self.assertEqual(validate_fhir_bundle(bundle), bundle)

    def test_fhir_patient_validation(self):
        patient = patient_reference('student@uni.de')
        self.assertEqual(validate_fhir_patient(patient), patient)


class ConfigValidationTests(unittest.TestCase):
    def test_validate_config_allows_prod_with_strong_secrets(self):
        original_env = config.ENV
        original_jwt = config.JWT_SECRET
        original_cors = config.CORS_ORIGIN
        try:
            config.ENV = 'prod'
            config.JWT_SECRET = 'x' * 40
            config.CORS_ORIGIN = 'https://example.com'
            config.validate_config()
        finally:
            config.ENV = original_env
            config.JWT_SECRET = original_jwt
            config.CORS_ORIGIN = original_cors


if __name__ == '__main__':
    unittest.main()
