"""Settings and accounts the tests use.

Everything here can be changed with an environment variable, so the same
tests run against any copy of the app without editing the code.
"""

import os
from dataclasses import dataclass

# Address of the app under test. Also used by pytest.ini through --base-url.
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
