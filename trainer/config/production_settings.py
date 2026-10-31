"""Production entry point; only the local nginx proxy may reach Gunicorn."""
from .stage2_settings import *

if not PRODUCTION:
    raise RuntimeError('TRAINER_PRODUCTION=1 is required')
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_TRUSTED_ORIGINS = ['https://' + host for host in ALLOWED_HOSTS if host not in {'localhost','127.0.0.1','[::1]'}]
STATIC_ROOT = Path(os.environ['TRAINER_STATIC_ROOT'])
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
SECURE_REFERRER_POLICY = 'same-origin'
MIDDLEWARE = ['learning.middleware.ProxyClientAddressMiddleware'] + MIDDLEWARE
