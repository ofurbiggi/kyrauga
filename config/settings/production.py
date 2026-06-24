from .base import *
import os
import dj_database_url

DEBUG = os.getenv("DEBUG", "False") == "True"

SECRET_KEY = os.environ["SECRET_KEY"]

ALLOWED_HOSTS = os.getenv(
    "ALLOWED_HOSTS",
    "kyrauga.is,www.kyrauga.is,kyrauga.herokuapp.com,.herokuapp.com",
).split(",")

CSRF_TRUSTED_ORIGINS = os.getenv(
    "CSRF_TRUSTED_ORIGINS",
    "https://kyrauga.is,https://www.kyrauga.is,https://kyrauga.herokuapp.com",
).split(",")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True") == "True"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("SECURE_HSTS_INCLUDE_SUBDOMAINS", "False") == "True"
SECURE_HSTS_PRELOAD = os.getenv("SECURE_HSTS_PRELOAD", "False") == "True"

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
