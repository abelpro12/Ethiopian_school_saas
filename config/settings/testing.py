"""
Testing settings for EthioSchool SaaS.
Inherits from development settings and overrides anything that would
interfere with the Django test runner.
"""
from .development import *  # noqa

# ─── Disable django-axes during tests ────────────────────────────────────────
# The AxesBackend requires a `request` object via authenticate(request=...).
# Django's TestClient.login() uses the default authenticate() path without
# a request, which causes AxesBackendRequestParameterRequired to be raised.
# Disabling axes during testing lets us keep the login brute-force protection
# in production without breaking the test suite.
AXES_ENABLED = False

# Remove AxesStandaloneBackend from AUTHENTICATION_BACKENDS to avoid any
# residual Axes checks during testing.
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

# ─── Speed up password hashing in tests ──────────────────────────────────────
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# ─── Use an in-memory SQLite database for speed ──────────────────────────────
# Override only if you want true DB isolation; comment out to use the dev DB.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# ─── Disable caching ─────────────────────────────────────────────────────────
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# ─── Use console email backend ────────────────────────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# ─── Disable Celery / background tasks ───────────────────────────────────────
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# ─── Webhook secret must be set even in tests to avoid ImproperlyConfigured ──
# The secure webhook verify_webhook_signature now raises ImproperlyConfigured
# if CHAPA_WEBHOOK_SECRET is missing. Provide a dummy value for test isolation.
CHAPA_WEBHOOK_SECRET = 'test-webhook-secret-do-not-use-in-production'
