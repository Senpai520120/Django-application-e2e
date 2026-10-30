"""Fail unless the tests read the expected sign-in mode from the running stack.

CI runs this before each E2E run, with E2E_AUTH unset. A wrong guess would
not fail the run by itself: it would quietly skip test_sso.py or test_ad.py.

    python e2e/tools/expect_auth.py keycloak
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402

expected = sys.argv[1]
if os.getenv("E2E_AUTH"):
    sys.exit("E2E_AUTH is set, so nothing is detected: unset it first.")
detected = config.AUTH
if detected != expected:
    sys.exit(f"The stack looks like {detected!r}, expected {expected!r}.")
print(f"sign-in mode detected: {detected}")
