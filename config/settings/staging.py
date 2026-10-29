import os
import sys
from .base import *

# ─── CORE STAGING SETTINGS ───────────────────────────────────────────────────
DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() in ('true', '1')

_raw_hosts = os.environ.get('ALLOWED_HOSTS', 'staging.saas.et,*.staging.saas.et,localhost,127.0.0.1')
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(',') if h.strip()]

# Staging secret key: must be set in environment for real deployments
SECRET_KEY = os.environ.get('SECRET_KEY', 'staging-secret-key-ethiopia-do-not-use-in-production')

# Fix @login_required redirect
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'

# HTTPS / Proxy Headers
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ─── TRUSTED PROXY IPS ───────────────────────────────────────────────────────
_raw_proxy_ips = os.environ.get('SECURE_PROXY_IPS', '127.0.0.1,::1')
SECURE_PROXY_IPS = {ip.strip() for ip in _raw_proxy_ips.split(',') if ip.strip()}

# ─── STAGING DATABASE SETUP ──────────────────────────────────────────────────
# Staging database configuration:
# 1. DATABASE_URL if provided (parsed via dj_database_url).
# 2. Individual POSTGRES_* or DB_* environment variables.
# 3. If no staging database environment variables are set, we fail-safe to an
#    in-memory SQLite database to NEVER touch a developer's local db.sqlite3.
_database_url = os.environ.get('DATABASE_URL', '').strip()

if _database_url:
    try:
        import dj_database_url
        DATABASES = {
            'default': dj_database_url.parse(
                _database_url,
                conn_max_age=600,
                conn_health_checks=True,
            )
        }
    except ImportError:
        raise RuntimeError(
            "DATABASE_URL is configured in staging, but 'dj-database-url' is not installed."
        )
elif os.environ.get('DB_NAME') or os.environ.get('POSTGRES_DB'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME') or os.environ.get('POSTGRES_DB', 'ethiopian_school_staging'),
            'USER': os.environ.get('DB_USER') or os.environ.get('POSTGRES_USER', 'postgres'),
            'PASSWORD': os.environ.get('DB_PASSWORD') or os.environ.get('POSTGRES_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST') or os.environ.get('POSTGRES_HOST', 'db'),
            'PORT': os.environ.get('DB_PORT') or os.environ.get('POSTGRES_PORT', '5432'),
            'CONN_MAX_AGE': 600,
        }
    }
else:
    # Staging requires explicit PostgreSQL configuration to prevent silent fallback to SQLite.
    # Offline system checks and test runners are permitted to use :memory: for safe introspection.
    is_test_runner = (
        'test' in sys.argv
        or 'check' in sys.argv
        or any('pytest' in str(arg).lower() for arg in sys.argv)
        or bool(os.environ.get('PYTEST_CURRENT_TEST'))
    )
    if os.environ.get('ALLOW_STAGING_MEMORY_DB', '').lower() in ('1', 'true') or is_test_runner:
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        }
    else:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured(
            "CRITICAL STAGING ERROR: Staging environment requires PostgreSQL database configuration via "
            "DATABASE_URL or POSTGRES_DB / DB_NAME environment variables. "
            "Silent fallback to in-memory SQLite during migrations or runtime is blocked."
        )

# ─── STAGING EMAIL / EXTERNAL SERVICE SAFEGUARDS ─────────────────────────────
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.locmem.EmailBackend')

