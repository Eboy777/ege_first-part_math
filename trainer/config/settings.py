import os
from pathlib import Path
from django.core.management.utils import get_random_secret_key
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BASE_DIR.parent
STATE_DIR = Path(os.environ.get('TRAINER_STATE_DIR', PROJECT_DIR / '.runtime'))
STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
PRODUCTION = os.environ.get('TRAINER_PRODUCTION') == '1'
SECRET_KEY = os.environ.get('TRAINER_SECRET_KEY')
if not SECRET_KEY:
    if PRODUCTION:
        raise RuntimeError('TRAINER_SECRET_KEY is required in production')
    key_file = STATE_DIR / 'secret.key'
    try:
        fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, 'w') as f:
            f.write(get_random_secret_key())
    SECRET_KEY = key_file.read_text()
DEBUG = False
ALLOWED_HOSTS = os.environ.get('TRAINER_ALLOWED_HOSTS', '127.0.0.1,localhost,[::1]').split(',')
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.staticfiles', 'learning']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'learning.middleware.ProtectedPagesMiddleware', 'learning.middleware.PrivateResponseMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.auth.context_processors.auth']}}]
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': STATE_DIR / 'trainer.sqlite3', 'OPTIONS': {'timeout': 20}}}
WSGI_APPLICATION = 'config.wsgi.application'
AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 10}}, {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'}, {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'}]
LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/login'
LOGIN_REDIRECT_URL = '/'
SESSION_COOKIE_NAME = 'pyaterka_session'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = PRODUCTION
CSRF_COOKIE_SECURE = PRODUCTION
SESSION_COOKIE_AGE = 43200
SESSION_SAVE_EVERY_REQUEST = False
SECURE_SSL_REDIRECT = PRODUCTION
SECURE_HSTS_SECONDS = 31536000 if PRODUCTION else 0
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
STATIC_URL = '/static/'
STATICFILES_DIRS = [('design-system', PROJECT_DIR / 'design-system')]
STATIC_ROOT = STATE_DIR / 'static'

TASK_ASSET_ROOT = PROJECT_DIR / 'assets' / 'tasks'
