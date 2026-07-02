"""HMAC-SHA256 JWT-style token auth (stdlib only)."""
import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from hashlib import pbkdf2_hmac

from server.config import JWT_SECRET, TOKEN_EXPIRY_HOURS

PASSWORD_HASH_ITERATIONS = 200_000
HASH_NAME = 'sha256'


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _b64url_decode(data: str) -> bytes:
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_token(email: str, first_name: str = '', last_name: str = '') -> str:
    header = {'alg': 'HS256', 'typ': 'JWT'}
    now = int(time.time())
    payload = {
        'sub': email.strip().lower(),
        'firstName': first_name,
        'lastName': last_name,
        'iat': now,
        'exp': now + TOKEN_EXPIRY_HOURS * 3600,
        'jti': uuid.uuid4().hex,
    }
    segments = [
        _b64url_encode(json.dumps(header, separators=(',', ':')).encode()),
        _b64url_encode(json.dumps(payload, separators=(',', ':')).encode()),
    ]
    signing_input = '.'.join(segments).encode()
    signature = hmac.new(JWT_SECRET.encode(), signing_input, hashlib.sha256).digest()
    segments.append(_b64url_encode(signature))
    return '.'.join(segments)


def hash_password(password: str, salt: bytes | str | None = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    elif isinstance(salt, str):
        salt = bytes.fromhex(salt)

    derived = pbkdf2_hmac(HASH_NAME, password.encode('utf-8'), salt, PASSWORD_HASH_ITERATIONS, dklen=32)
    return f'pbkdf2_{HASH_NAME}${PASSWORD_HASH_ITERATIONS}${salt.hex()}${derived.hex()}'


def verify_password(password: str, stored_hash_salt: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored_hash_salt.split('$')
        if algorithm != f'pbkdf2_{HASH_NAME}':
            return False
        salt = bytes.fromhex(salt_hex)
        expected = pbkdf2_hmac(HASH_NAME, password.encode('utf-8'), salt, int(iterations), dklen=32)
        return hmac.compare_digest(expected.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def verify_token(token: str) -> dict | None:
    if not token:
        return None
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        signing_input = f'{parts[0]}.{parts[1]}'.encode()
        expected_sig = hmac.new(JWT_SECRET.encode(), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url_encode(expected_sig), parts[2]):
            return None
        payload = json.loads(_b64url_decode(parts[1]))
        if payload.get('exp', 0) < int(time.time()):
            return None
        return payload
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def extract_bearer_token(auth_header: str | None) -> str | None:
    if not auth_header:
        return None
    parts = auth_header.split(' ', 1)
    if len(parts) == 2 and parts[0].lower() == 'bearer':
        return parts[1].strip()
    return None
