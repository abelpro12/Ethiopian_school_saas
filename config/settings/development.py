from .base import *

DEBUG = True
ALLOWED_HOSTS = ['*']

# Fix @login_required redirect to use our custom login page
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'

# Disable secure cookies for local HTTP development
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
