import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-ethiopian-school-saas-dev-key')

DEBUG = True

ALLOWED_HOSTS = ['*']

CSRF_TRUSTED_ORIGINS = [
    'http://127.0.0.1:8000',
    'http://localhost:8000',
    'http://127.0.0.1',
    'http://localhost',
    'http://*.localhost',
    'http://*.localhost:8000',
]

CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True
CSRF_USE_SESSIONS = False
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 14400  # 4 hours

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party
    'rest_framework',
    'drf_spectacular',    # OpenAPI 3.0 / Swagger docs
    'corsheaders',
    'axes',              # Login rate limiting (django-axes)
    'dbbackup',          # Database backups

    # Project Apps
    'apps.tenants',
    'apps.accounts',
    'apps.schools',
    'apps.subscriptions',
    'apps.academics',
    'apps.students',
    'apps.parents',
    'apps.teachers',
    'apps.enrollment',
    'apps.attendance',
    'apps.assessments',
    'apps.examinations',
    'apps.grading',
    'apps.rankings',
    'apps.finance',
    'apps.payments',
    'apps.communication',
    'apps.reports',
    'apps.documents',
    'apps.audit',
    'apps.api',
    'apps.support',
    'apps.messaging',
    'apps.homework',
    'apps.discipline',
    'apps.library',
    'apps.hr',
    'apps.timetable',
    'apps.platform_management',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'axes.middleware.AxesMiddleware',   # Must be after AuthenticationMiddleware
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    # Tenant & Audit Custom Middleware
    'apps.tenants.middleware.TenantMiddleware',
    'apps.academics.middleware.AcademicYearMiddleware',
    'apps.academics.middleware.CalendarPreferenceMiddleware',
    'apps.subscriptions.middleware.SubscriptionMiddleware',
    'apps.audit.middleware.AuditLogMiddleware',

    # Security: Redirect users with must_change_password=True to password change page
    'apps.accounts.middleware.ForcePasswordChangeMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.tenants.context_processors.tenant_context',
                'apps.academics.context_processors.academic_year_context',
                'apps.academics.context_processors.calendar_preference_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTH_USER_MODEL = 'accounts.User'

# django-axes requires AxesBackend to be added alongside ModelBackend
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',  # Must be first
    'django.contrib.auth.backends.ModelBackend',
]

# Login / logout URL configuration
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

# ─── DJANGO-AXES DEFAULTS (overridden per environment) ───────────────────────
# Default: permissive in dev, strict in production.py
AXES_FAILURE_LIMIT = 10        # Allow 10 attempts in development
AXES_COOLOFF_TIME = None       # No lockout by default (production overrides)
AXES_LOCKOUT_URL = '/login/?locked=1'
AXES_RESET_ON_SUCCESS = True
AXES_ENABLE_ADMIN = True
AXES_CACHE = 'default'

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Africa/Addis_Ababa'

USE_I18N = True

USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '30/minute',
        'user': '300/minute',
        'auth_sensitive': '5/minute',
    },
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
}

# ─── DRF SPECTACULAR (OPENAPI 3.0 / SWAGGER DOCS) ────────────────────────────
SPECTACULAR_SETTINGS = {
    'TITLE': 'EthioSchool SaaS REST API',
    'DESCRIPTION': 'Production OpenAPI 3.0 REST API documentation for EthioSchool Multi-Tenant Ethiopian School Management SaaS.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_PATCH': True,
    'COMPONENT_SPLIT_REQUEST': True,
}

# ─── REAL-TIME ERROR MONITORING (SENTRY SDK) ──────────────────────────────────
SENTRY_DSN = os.environ.get('SENTRY_DSN')
if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.redis import RedisIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[
                DjangoIntegration(),
                CeleryIntegration(),
                RedisIntegration(),
            ],
            traces_sample_rate=float(os.environ.get('SENTRY_TRACES_SAMPLE_RATE', '0.1')),
            send_default_pii=False,
            environment=os.environ.get('ENVIRONMENT', 'development' if DEBUG else 'production'),
        )
    except Exception as e:
        import logging
        logging.warning(f"Failed to initialize Sentry SDK: {e}")

from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),   # Access token valid for 60 minutes
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),       # Refresh token valid for 7 days
    'ROTATE_REFRESH_TOKENS': True,                     # Issue a new refresh token on refresh
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),                  # Header format: Authorization: Bearer <token>
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    'nightly_database_backup': {
        'task': 'apps.platform_management.tasks.run_automated_database_backup',
        'schedule': crontab(hour=2, minute=0),  # Runs at 2:00 AM every night
    },
}
CHAPA_SECRET_KEY = os.environ.get('CHAPA_SECRET_KEY', 'CHASECK_TEST-sample-secret-key-ethiopia')
CHAPA_PUBLIC_KEY = os.environ.get('CHAPA_PUBLIC_KEY', 'CHAPUBK_TEST-sample-public-key-ethiopia')
CHAPA_WEBHOOK_SECRET = os.environ.get('CHAPA_WEBHOOK_SECRET', 'sample-webhook-secret-key')


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'django_application.log',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
        },
        'django.security': {
            'handlers': ['console', 'file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'payments': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

import sys
if 'test' in sys.argv:
    AXES_ENABLED = False

