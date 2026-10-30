"""Settings and accounts the tests use.

Everything here can be changed with an environment variable, so the same
tests run against any copy of the app without editing the code.
"""

import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

# Address of the app under test. Used by the base_url fixture in conftest.py;
# `pytest --base-url ...` on the command line wins over it.
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")

# Password of every demo_* account created by `manage.py seed_demo_users`.
DEMO_PASSWORD = os.getenv("E2E_PASSWORD", "demo-password-123")

# Must be the same as FILE_MANAGER_MAX_FILE_SIZE of the app (5 MB in docker-compose).
MAX_FILE_SIZE = int(os.getenv("E2E_MAX_FILE_SIZE", str(5 * 1024 * 1024)))

# Password for users that the tests create. It passes every Django password check.
NEW_USER_PASSWORD = "E2e-Strong-Pass-42"


@dataclass(frozen=True)
class User:
    username: str
    password: str = DEMO_PASSWORD


# Demo accounts that already exist in the app.
ADMIN = User("demo_admin")  # member of the "admin" role, can open /manage/
REGULAR_USER = User("demo_user")  # member of the "user" role, gets 403 on /manage/
INACTIVE_USER = User("demo_inactive")  # switched off, cannot sign in

# --- sign-in through Keycloak (docker-compose.sso.yml) ---

# The realm as the browser sees it.
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8080/realms/myapp")

# Accounts that exist only in Keycloak (keycloak/realm-myapp.json).
KC_DISABLED = User("kc_disabled")  # switched off in Keycloak
KC_NEWCOMER = User("kc_newcomer")  # not in the app until the first sign-in
KC_PROMOTED = User("kc_promoted")  # gets the admin role in the panel during a test

# --- Active Directory (Samba, docker-compose.ad.yml) ---

# LDAPS of the test domain controller, published on the host for the tests.
AD_URL = os.getenv("E2E_AD_URL", "ldaps://127.0.0.1:6636")
AD_ADMIN = os.getenv("E2E_AD_ADMIN", "Administrator@corp.example.test")
AD_ADMIN_PASSWORD = os.getenv("E2E_AD_ADMIN_PASSWORD", "Samba-admin-123")
AD_USERS_DN = "CN=Users,DC=corp,DC=example,DC=test"
AD_EMAIL_DOMAIN = "corp.example.test"

# --- which sign-in the app under test uses ---


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def detect_auth() -> str:
    """The sign-in mode of the running stack, read from the app itself.

    With SSO on, /login/ hands over to /oidc/authenticate/ instead of showing
    the app's own form. AD is told apart by its LDAPS port, which only the
    stack with docker-compose.ad.yml publishes. An app that does not answer
    counts as "local": the tests then fail on it with a clear error.
    """
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        opener.open(f"{BASE_URL}/login/", timeout=5)
        return "local"
    except urllib.error.HTTPError as error:
        if "/oidc/" not in error.headers.get("Location", ""):
            return "local"
    except OSError:
        return "local"

    ad = urllib.parse.urlparse(AD_URL)
    try:
        socket.create_connection((ad.hostname, ad.port or 636), timeout=2).close()
    except OSError:
        return "keycloak"
    return "ad"


# local: the app's own sign-in form; tests/test_sso.py and test_ad.py are skipped.
# keycloak: the tests fill the Keycloak form instead; tests of the app's own
#   form are skipped, tests/test_sso.py runs.
# ad: the same, with Active Directory behind Keycloak; tests/test_ad.py runs too.
# E2E_AUTH forces a mode; unset, it is read from the running stack.
AUTH_SOURCE = "E2E_AUTH" if os.getenv("E2E_AUTH") else "detected"
AUTH = os.getenv("E2E_AUTH") or detect_auth()
SSO = AUTH in ("keycloak", "ad")
AD = AUTH == "ad"
