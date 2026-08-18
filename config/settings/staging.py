from .base import *

DEBUG = True  # Verbose debug output for staging tests
ALLOWED_HOSTS = ['staging.saas.et', '*.staging.saas.et', 'localhost', '127.0.0.1']

# Staging Database Setup
import os
import dj_database_url if 'dj_database_url' in sys.modules else None

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
