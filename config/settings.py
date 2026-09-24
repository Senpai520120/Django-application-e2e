"""Project settings. Secrets and environment come from .env, see .env.example."""

from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    SECRET_KEY=(str, ""),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1", "[::1]"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    DATABASE_URL=(str, f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
    SESSION_COOKIE_SECURE=(bool, False),
    CSRF_COOKIE_SECURE=(bool, False),
    SECURE_SSL_REDIRECT=(bool, False),
    SECURE_HSTS_SECONDS=(int, 0),
    SECURE_HSTS_INCLUDE_SUBDOMAINS=(bool, False),
    SECURE_HSTS_PRELOAD=(bool, False),
    FILE_STORAGE_BACKEND=(str, "local"),
    FILE_MANAGER_MAX_FILE_SIZE=(int, 25 * 1024 * 1024),
    FILE_MANAGER_MAX_TOTAL_SIZE=(int, 512 * 1024 * 1024),
)

environ.Env.read_env(BASE_DIR / ".env")

DEBUG = env("DEBUG")

SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured(
        "SECRET_KEY is not set. Copy .env.example to .env and fill it in."
    )
if SECRET_KEY == "change-me" and not DEBUG:
    raise ImproperlyConfigured("SECRET_KEY is still the .env.example placeholder.")

ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "panel",
    "files",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.panel_access",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {"default": env.db_url("DATABASE_URL")}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
        )
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# The manifest backend requires collectstatic, so development uses the plain one.
_default_staticfiles_backend = (
    "django.contrib.staticfiles.storage.StaticFilesStorage"
    if DEBUG
    else "whitenoise.storage.CompressedManifestStaticFilesStorage"
)
# File manager: local is the server disk, s3 is a bucket via django-storages.
FILE_STORAGE_BACKEND = env("FILE_STORAGE_BACKEND")
_default_file_backends = {
    "local": "django.core.files.storage.FileSystemStorage",
    "s3": "storages.backends.s3.S3Storage",
}
if FILE_STORAGE_BACKEND not in _default_file_backends:
    raise ImproperlyConfigured(
        f"FILE_STORAGE_BACKEND={FILE_STORAGE_BACKEND!r}: expected local or s3."
    )

STORAGES = {
    "default": {"BACKEND": _default_file_backends[FILE_STORAGE_BACKEND]},
    "staticfiles": {
        "BACKEND": env("STATICFILES_BACKEND", default=_default_staticfiles_backend)
    },
}

FILE_MANAGER = {
    "BACKEND": FILE_STORAGE_BACKEND,
    "ROOT": env("FILE_MANAGER_ROOT", default=str(BASE_DIR / "filemanager")),
    "S3_LOCATION": env("FILE_MANAGER_S3_LOCATION", default="filemanager"),
    "MAX_FILE_SIZE": env("FILE_MANAGER_MAX_FILE_SIZE"),
    "MAX_TOTAL_SIZE": env("FILE_MANAGER_MAX_TOTAL_SIZE"),
}

# Read by django-storages. Keys are never stored in code: either the environment
# or the instance IAM role when the variables are left unset.
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="")
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="eu-central-1")
AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default=None)
# S3 emulators (localstack, moto) cannot do virtual-hosted addressing.
AWS_S3_ADDRESSING_STYLE = env("AWS_S3_ADDRESSING_STYLE", default=None)
AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default=None)
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default=None)
AWS_DEFAULT_ACL = None
AWS_S3_FILE_OVERWRITE = False
AWS_QUERYSTRING_AUTH = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Turn these on behind HTTPS only: over plain http the browser drops the secure
# cookie and login stops working.
SESSION_COOKIE_SECURE = env("SESSION_COOKIE_SECURE")
CSRF_COOKIE_SECURE = env("CSRF_COOKIE_SECURE")
SECURE_SSL_REDIRECT = env("SECURE_SSL_REDIRECT")
SECURE_HSTS_SECONDS = env("SECURE_HSTS_SECONDS")
SECURE_HSTS_INCLUDE_SUBDOMAINS = env("SECURE_HSTS_INCLUDE_SUBDOMAINS")
SECURE_HSTS_PRELOAD = env("SECURE_HSTS_PRELOAD")
# Behind a TLS-terminating proxy; without it SECURE_SSL_REDIRECT loops forever.
if env.bool("USE_X_FORWARDED_PROTO", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.request": {"level": "ERROR", "propagate": True},
    },
}
