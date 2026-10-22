"""Project settings. Secrets and environment come from .env, see .env.example."""

from pathlib import Path

import environ
from django.conf import global_settings
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

# Sign-in through Keycloak (OpenID Connect) instead of the local form.
# Keycloak answers "who you are"; roles and switching a user off stay in the
# panel. Off by default; docker-compose.sso.yml turns it on.
OIDC_ENABLED = env.bool("OIDC_ENABLED", default=False)
if OIDC_ENABLED:
    INSTALLED_APPS.append("mozilla_django_oidc")
    # Keycloak is the only way in: without ModelBackend a local password
    # (at /admin/login/, say) cannot get around a user disabled in Keycloak.
    AUTHENTICATION_BACKENDS = ["accounts.oidc.KeycloakBackend"]
    # Two addresses of the same realm: the browser reaches Keycloak at
    # localhost:8080, the app inside docker at keycloak:8080.
    _browser = env("OIDC_BROWSER_URL") + "/protocol/openid-connect"
    _backend = env("OIDC_BACKEND_URL", default=env("OIDC_BROWSER_URL"))
    _backend += "/protocol/openid-connect"

    OIDC_RP_CLIENT_ID = env("OIDC_RP_CLIENT_ID")
    OIDC_RP_CLIENT_SECRET = env("OIDC_RP_CLIENT_SECRET")
    OIDC_RP_SIGN_ALGO = "RS256"
    OIDC_RP_SCOPES = "openid email profile"
    OIDC_USE_PKCE = True
    OIDC_OP_AUTHORIZATION_ENDPOINT = f"{_browser}/auth"
    OIDC_OP_LOGOUT_ENDPOINT = f"{_browser}/logout"
    OIDC_OP_TOKEN_ENDPOINT = f"{_backend}/token"
    OIDC_OP_USER_ENDPOINT = f"{_backend}/userinfo"
    OIDC_OP_JWKS_ENDPOINT = f"{_backend}/certs"
    # The id token goes back to Keycloak on sign-out as id_token_hint.
    OIDC_STORE_ID_TOKEN = True
    OIDC_OP_LOGOUT_URL_METHOD = "accounts.oidc.keycloak_logout_url"
    # Where Keycloak sends the browser after sign-out. Empty: the app's own
    # address as the request saw it, which behind a proxy needs
    # USE_X_FORWARDED_PROTO to come out as https.
    OIDC_POST_LOGOUT_REDIRECT_URL = env("OIDC_POST_LOGOUT_REDIRECT_URL", default="")
    LOGIN_URL = "oidc_authentication_init"
    # Not "/": that page needs a signed-in user, so a refused user would go
    # to Keycloak, which still remembers them, and back here in a loop.
    # A path, not a URL name: mozilla-django-oidc redirects to it as is.
    LOGIN_REDIRECT_URL_FAILURE = "/login/failed/"

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
# FILE_STORAGE_BACKEND picks the backend the way DATABASE_URL picks the
# database: "local", "s3", or the dotted path of any other
# files.storage.FileManagerStorage subclass. The file manager reads
# STORAGES["filemanager"], so a third backend is a class plus this variable.
FILE_STORAGE_BACKEND = env("FILE_STORAGE_BACKEND")
_file_backends = {
    "local": {
        "default": "django.core.files.storage.FileSystemStorage",
        "filemanager": "files.storage.LocalFileStorage",
        "OPTIONS": {
            "location": env("FILE_MANAGER_ROOT", default=str(BASE_DIR / "filemanager"))
        },
    },
    "s3": {
        "default": "storages.backends.s3.S3Storage",
        "filemanager": "files.storage.S3FileStorage",
        "OPTIONS": {"location": env("FILE_MANAGER_S3_LOCATION", default="filemanager")},
    },
}
if FILE_STORAGE_BACKEND in _file_backends:
    _file_backend = _file_backends[FILE_STORAGE_BACKEND]
elif "." in FILE_STORAGE_BACKEND:
    # A custom backend reads its own settings, like any Django storage.
    _file_backend = {
        "default": _file_backends["local"]["default"],
        "filemanager": FILE_STORAGE_BACKEND,
        "OPTIONS": {},
    }
else:
    raise ImproperlyConfigured(
        f"FILE_STORAGE_BACKEND={FILE_STORAGE_BACKEND!r}: expected local, s3 "
        "or the dotted path of a FileManagerStorage subclass."
    )

STORAGES = {
    "default": {"BACKEND": _file_backend["default"]},
    "filemanager": {
        "BACKEND": _file_backend["filemanager"],
        "OPTIONS": _file_backend["OPTIONS"],
    },
    "staticfiles": {
        "BACKEND": env("STATICFILES_BACKEND", default=_default_staticfiles_backend)
    },
}

FILE_MANAGER = {
    "MAX_FILE_SIZE": env("FILE_MANAGER_MAX_FILE_SIZE"),
    # A soft limit: checked before saving, without a lock, so uploads running
    # at the same moment can pass it together by at most one batch each.
    "MAX_TOTAL_SIZE": env("FILE_MANAGER_MAX_TOTAL_SIZE"),
}

# The size limit is enforced while a file arrives, before it reaches the disk.
FILE_UPLOAD_HANDLERS = [
    "files.uploads.SizeLimitUploadHandler",
    *global_settings.FILE_UPLOAD_HANDLERS,
]

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
