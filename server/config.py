"""Environment-aware configuration (dev / stage / prod)."""
import os

ENV = os.environ.get('MINDBRIDGE_ENV', 'dev').lower()

CONFIG = {
    'dev': {
        'debug': True,
        'token_expiry_hours': 72,
        'cors_origin': '*',
        'require_tls': False,
    },
    'stage': {
        'debug': False,
        'token_expiry_hours': 24,
        'cors_origin': os.environ.get('CORS_ORIGIN', '*'),
        'require_tls': False,
    },
    'prod': {
        'debug': False,
        'token_expiry_hours': 12,
        'cors_origin': os.environ.get('CORS_ORIGIN', ''),
        'require_tls': True,
    },
}

_settings = CONFIG.get(ENV, CONFIG['dev'])

DEBUG = _settings['debug']
TOKEN_EXPIRY_HOURS = _settings['token_expiry_hours']
CORS_ORIGIN = _settings['cors_origin']
REQUIRE_TLS = _settings['require_tls']

JWT_SECRET = os.environ.get('JWT_SECRET', 'dev-only-change-in-production')
DB_PATH = os.environ.get('DB_PATH', 'mindbridge.db')
PORT = int(os.environ.get('PORT', '8000'))


class ConfigError(Exception):
    pass


def validate_config() -> None:
    if ENV in ('stage', 'prod'):
        if JWT_SECRET == 'dev-only-change-in-production' or not JWT_SECRET or len(JWT_SECRET) < 32:
            raise ConfigError(
                'JWT_SECRET must be set to a strong secret of at least 32 characters in stage/prod'
            )

    if ENV == 'prod':
        if not CORS_ORIGIN or CORS_ORIGIN == '*':
            raise ConfigError('CORS_ORIGIN must be set to a specific origin in production')

    if not DB_PATH:
        raise ConfigError('DB_PATH must be configured')
