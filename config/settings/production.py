from .base import *
import os
import dj_database_url

DEBUG = False

# ManifestStaticFilesStorage is recommended in production, to prevent
# outdated JavaScript / CSS assets being served from cache
# (e.g. after a Wagtail upgrade).
# See https://docs.djangoproject.com/en/6.0/ref/contrib/staticfiles/#manifeststaticfilesstorage
STORAGES["staticfiles"]["BACKEND"] = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"

try:
    from .local import *
except ImportError:
    pass


DEBUG = os.getenv("DEBUG", "False") == "True"

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost").split(",")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # ...
]

STATIC_ROOT = BASE_DIR / "staticfiles"

if "DATABASE_URL" in os.environ:
    DATABASES["default"] = dj_database_url.config(
        conn_max_age=600,
        ssl_require=True
    )