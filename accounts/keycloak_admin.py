"""Creating Keycloak accounts for users made in the app.

With SSO on, nobody signs in with a Django password, so a user created in the
panel, or before SSO was switched on, needs a Keycloak account too. Django
keeps only a hash of the password; Keycloak accepts that hash as it is
(pbkdf2-sha256, the format of Django's default hasher), so the user signs in
to Keycloak with the very same password.

The app calls the Admin API as the service account of its own client, which
the realm gives only the view-users and manage-users roles.
"""

import base64
import json

import requests
from django.conf import settings

from accounts.models import KeycloakIdentity

TIMEOUT = 5


class KeycloakUnavailable(Exception):
    """Keycloak did not answer, or answered with something unexpected."""


class KeycloakUserExists(Exception):
    """Keycloak already has an account with this username."""


def credential_from_hash(encoded):
    """Keycloak's form of a Django password hash, or None if it cannot take it.

    Django: pbkdf2_sha256$<iterations>$<salt>$<base64 hash>. Keycloak wants
    the same hash and iterations, and the salt as base64 of its bytes.
    """
    try:
        algorithm, iterations, salt, value = encoded.split("$")
    except (AttributeError, ValueError):
        return None
    if algorithm != "pbkdf2_sha256":
        return None
    return {
        "type": "password",
        "credentialData": json.dumps(
            {
                "hashIterations": int(iterations),
                "algorithm": "pbkdf2-sha256",
                "additionalParameters": {},
            }
        ),
        "secretData": json.dumps(
            {
                "value": value,
                "salt": base64.b64encode(salt.encode()).decode(),
                "additionalParameters": {},
            }
        ),
    }


def push_user(user):
    """Create the Keycloak account of a Django user and link the two.

    Returns the Keycloak id. A user whose password Keycloak cannot take
    (none set, or another hasher) gets an account without a password.
    """
    account = {
        "username": user.username,
        "enabled": user.is_active,
        "firstName": user.first_name,
        "lastName": user.last_name,
    }
    if user.email:
        account.update(email=user.email, emailVerified=True)
    credential = credential_from_hash(user.password)
    if credential:
        account["credentials"] = [credential]

    response = call("post", "/users", json=account)
    if response.status_code == 409:
        raise KeycloakUserExists(user.username)
    if response.status_code != 201:
        raise KeycloakUnavailable(f"creating {user.username}: {response.status_code}")
    # 201 Created names the new account in Location: .../users/<id>
    sub = response.headers["Location"].rstrip("/").rsplit("/", 1)[-1]
    KeycloakIdentity.objects.create(user=user, sub=sub)
    return sub


def call(method, path, **kwargs):
    """One Admin API request with a fresh service-account token."""
    try:
        token = requests.post(
            settings.OIDC_OP_TOKEN_ENDPOINT,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.OIDC_RP_CLIENT_ID,
                "client_secret": settings.OIDC_RP_CLIENT_SECRET,
            },
            timeout=TIMEOUT,
        )
        token.raise_for_status()
        return requests.request(
            method,
            settings.OIDC_ADMIN_URL + path,
            headers={"Authorization": f"Bearer {token.json()['access_token']}"},
            timeout=TIMEOUT,
            **kwargs,
        )
    except (requests.RequestException, ValueError, KeyError) as error:
        raise KeycloakUnavailable(str(error)) from error
