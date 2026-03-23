from .base import *
import os
import dj_database_url

DEBUG = os.getenv("DEBUG", "False") == "True"

SECRET_KEY = os.environ["SECRET_KEY"]

ALLOWED_HOSTS = os.getenv(
    "ALLOWED_HOSTS",
    ".herokuapp.com,kyrauga.herokuapp.com"
).split(",")

CSRF_TRUSTED_ORIGINS = os.getenv(
    "CSRF_TRUSTED_ORIGINS",
    "https://kyrauga.herokuapp.com"
).split(",")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Keep all middleware from base.py, just insert WhiteNoise after SecurityMiddleware
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

# Use hashed static files in production
STORAGES["staticfiles"]["BACKEND"] = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
)

STATIC_ROOT = BASE_DIR / "staticfiles"

if "DATABASE_URL" in os.environ:
    DATABASES["default"] = dj_database_url.config(
        conn_max_age=600,
        ssl_require=True,
    )

try:
    from .local import *
except ImportError:
    pass