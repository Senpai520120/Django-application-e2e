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
import time

import requests
from django.conf import settings

from accounts.models import KeycloakIdentity

TIMEOUT = 5


class KeycloakUnavailable(Exception):
    """Keycloak did not answer, or answered with something unexpected."""


class KeycloakUserExists(Exception):
    """Keycloak already has an account with this username."""


class KeycloakRefused(Exception):
    """Keycloak would not create the account, for example: email taken.

    The message is Keycloak's own, meant to be shown to the admin.
    """


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
        # 409 also means "same email", which is not the same account.
        message = error_message(response)
        if "email" in message.lower():
            raise KeycloakRefused(message)
        raise KeycloakUserExists(user.username)
    if response.status_code != 201:
        raise KeycloakUnavailable(f"creating {user.username}: {response.status_code}")
    # 201 Created names the new account in Location: .../users/<id>
    sub = response.headers["Location"].rstrip("/").rsplit("/", 1)[-1]
    KeycloakIdentity.objects.create(user=user, sub=sub)
    return sub


def push_password(user):
    """Give the user's Keycloak account the password just set in Django.

    Otherwise the old password keeps working on the Keycloak form, the only
    way in with SSO on. Returns False when there is nothing to send to: no
    linked account yet (it gets the password when it is made), an account
    Keycloak has lost (push_users_to_keycloak makes it again with this very
    password), or a password Keycloak cannot take.
    """
    link = KeycloakIdentity.objects.filter(user=user).first()
    credential = credential_from_hash(user.password)
    if link is None or credential is None:
        return False
    response = call("put", f"/users/{link.sub}", json={"credentials": [credential]})
    if response.status_code == 404:
        return False
    if response.status_code != 204:
        raise KeycloakUnavailable(
            f"password of {user.username}: {response.status_code}"
        )
    return True


def in_directory(user):
    """Whether Keycloak finds this user's name or email in Active Directory.

    Keycloak looks the name and the email up in its User Federation too
    (Active Directory over LDAP) and marks what it found there with a
    federationLink. Such a person signs in with the AD password and is linked
    on the first sign-in; a Keycloak account of their own would be a second one.
    """
    lookups = [{"username": user.username}]
    if user.email:
        lookups.append({"email": user.email})
    for params in lookups:
        response = call("get", "/users", params={**params, "exact": "true"})
        try:
            accounts = response.json() if response.status_code == 200 else None
        except ValueError:
            accounts = None
        if not isinstance(accounts, list):
            raise KeycloakUnavailable(f"looking up {params}: {response.status_code}")
        if any(account.get("federationLink") for account in accounts):
            return True
    return False


def account_exists(sub):
    """Whether Keycloak still has the account with this id.

    In development Keycloak keeps its data inside its container: after
    `docker compose down` it starts again with the realm file only, and
    the accounts the app made are gone while the links in Django remain.
    """
    response = call("get", f"/users/{sub}")
    if response.status_code == 404:
        return False
    if response.status_code != 200:
        raise KeycloakUnavailable(f"looking up {sub}: {response.status_code}")
    return True


def error_message(response):
    try:
        return str(response.json().get("errorMessage", ""))
    except (ValueError, AttributeError):
        return ""


# The service-account token, reused until shortly before it expires:
# pushing many users at start would otherwise ask for one per request.
_token = {"value": None, "expires": 0.0}


def service_token():
    if _token["value"] and time.monotonic() < _token["expires"]:
        return _token["value"]
    response = requests.post(
        settings.OIDC_OP_TOKEN_ENDPOINT,
        data={
            "grant_type": "client_credentials",
            "client_id": settings.OIDC_RP_CLIENT_ID,
            "client_secret": settings.OIDC_RP_CLIENT_SECRET,
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    body = response.json()
    _token["value"] = body["access_token"]
    _token["expires"] = time.monotonic() + int(body.get("expires_in", 60)) - 30
    return _token["value"]


def call(method, path, **kwargs):
    """One Admin API request as the app's service account."""
    try:
        return requests.request(
            method,
            settings.OIDC_ADMIN_URL + path,
            headers={"Authorization": f"Bearer {service_token()}"},
            timeout=TIMEOUT,
            **kwargs,
        )
    except (requests.RequestException, ValueError, KeyError) as error:
        raise KeycloakUnavailable(str(error)) from error
