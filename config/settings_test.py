"""Test settings: independent of .env and of collected static files."""

import os

# Set before importing the main settings: they validate SECRET_KEY at import
# time, and read_env never overwrites variables already present in the env.
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("DEBUG", "False")
# A developer's .env may switch SSO or S3 on; the suite expects neither,
# the same as in CI, and the tests that need them turn them on themselves.
os.environ.setdefault("OIDC_ENABLED", "False")
os.environ.setdefault("FILE_STORAGE_BACKEND", "local")

from .settings import *  # noqa: E402, F403

# The whitenoise manifest requires collectstatic, which tests do not need.
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Tests create dozens of users, and PBKDF2 turns that into visible seconds.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
