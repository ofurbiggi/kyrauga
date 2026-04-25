from .base import *
from django.core.management.utils import get_random_secret_key
import os

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# Local development can use a real SECRET_KEY from the environment, but falls back
# to a process-local generated key so we do not commit one to the repository.
SECRET_KEY = os.getenv("SECRET_KEY", get_random_secret_key())

# SECURITY WARNING: define the correct hosts in production!
ALLOWED_HOSTS = ["*"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Local development and tests render templates without running collectstatic first.
# Production keeps WhiteNoise's compressed manifest storage in production.py.
STORAGES["staticfiles"]["BACKEND"] = "django.contrib.staticfiles.storage.StaticFilesStorage"


try:
    from .local import *
except ImportError:
    pass
