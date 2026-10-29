"""Settings and accounts the tests use.

Everything here can be changed with an environment variable, so the same
tests run against any copy of the app without editing the code.
"""

import os
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

# E2E_AUTH=keycloak: the app sends sign-in to Keycloak, and the tests fill
# the Keycloak form instead of the app's own. Tests of the app's own form
# are skipped then, and tests/test_sso.py runs.
# E2E_AUTH=ad: the same, with Active Directory behind Keycloak
# (docker-compose.ad.yml), and tests/test_ad.py runs too.
AUTH = os.getenv("E2E_AUTH", "local")
SSO = AUTH in ("keycloak", "ad")
AD = AUTH == "ad"

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
