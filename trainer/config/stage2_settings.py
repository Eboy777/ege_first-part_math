# Isolated UI routes: the parallel bank-preparation work keeps config.urls.
from .settings import *
ROOT_URLCONF = 'config.stage2_urls'

TRAINER_EXAM_VERSION = os.environ.get('TRAINER_EXAM_VERSION', 'ege_profile_2026')

DATABASES['default']['OPTIONS']['transaction_mode']='IMMEDIATE'
