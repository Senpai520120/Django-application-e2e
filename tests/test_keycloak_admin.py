"""Keycloak accounts for users made in the app: the panel and the switch to SSO.

Keycloak is replaced by FakeKeycloak below; that Keycloak really accepts
the hashes was checked against a live one (see accounts/keycloak_admin.py).
"""

import base64
import json
from io import StringIO
from unittest.mock import patch

import pytest
import requests
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.urls import reverse

from accounts import keycloak_admin
from accounts.keycloak_admin import (
    KeycloakUnavailable,
    KeycloakUserExists,
    credential_from_hash,
    push_user,
)
from accounts.models import KeycloakIdentity

DJANGO_HASH = "pbkdf2_sha256$1000000$s4lt$aGFzaA=="

SSO_SETTINGS = {
    "OIDC_ENABLED": True,
    "OIDC_RP_CLIENT_ID": "django-app",
    "OIDC_RP_CLIENT_SECRET": "test-secret",
    "OIDC_OP_TOKEN_ENDPOINT": "http://kc/realms/myapp/protocol/openid-connect/token",
    "OIDC_ADMIN_URL": "http://kc/admin/realms/myapp",
}


class FakeResponse:
    def __init__(self, status_code, body=None, headers=None):
        self.status_code = status_code
        self._body = body or {}
        self.headers = headers or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(self.status_code)


class FakeKeycloak:
    """Answers the token and create-user calls; remembers created accounts."""

    def __init__(self):
        self.accounts = {}
        self.down = False
        self.tokens_given = 0

    def post(self, url, data, timeout):
        if self.down:
            raise requests.ConnectionError("connection refused")
        assert data["grant_type"] == "client_credentials"
        self.tokens_given += 1
        return FakeResponse(200, {"access_token": "service-token", "expires_in": 300})

    def request(self, method, url, headers, timeout, json=None):
        if self.down:
            raise requests.ConnectionError("connection refused")
        assert headers == {"Authorization": "Bearer service-token"}
        users_url = "http://kc/admin/realms/myapp/users"
        if method == "get":
            sub = url.removeprefix(users_url + "/")
            ids = {account["id"] for account in self.accounts.values()}
            return FakeResponse(200 if sub in ids else 404)
        assert (method, url) == ("post", users_url)
        if json["username"] in self.accounts:
            return FakeResponse(409, {"errorMessage": "User exists with same username"})
        emails = {account.get("email") for account in self.accounts.values()}
        if json.get("email") and json["email"] in emails:
            return FakeResponse(409, {"errorMessage": "User exists with same email"})
        sub = f"kc-{len(self.accounts) + 1}"
        self.accounts[json["username"]] = {**json, "id": sub}
        return FakeResponse(201, headers={"Location": f"{url}/{sub}"})


@pytest.fixture
def keycloak(settings):
    # Load the URLconf in the local sign-in mode before SSO is switched on:
    # the mode is picked once, on the first import.
    reverse("home")
    for name, value in SSO_SETTINGS.items():
        setattr(settings, name, value)
    settings.KEYCLOAK_REMAKE_LOST_ACCOUNTS = False
    # The service-account token is kept between calls; not between tests.
    patch.dict(keycloak_admin._token, {"value": None, "expires": 0.0}).start()
    fake = FakeKeycloak()
    with (
        patch("accounts.keycloak_admin.requests.post", fake.post),
        patch("accounts.keycloak_admin.requests.request", fake.request),
    ):
        yield fake
    patch.stopall()


# --- the password hash ---


def test_django_hash_becomes_a_keycloak_credential():
    credential = credential_from_hash(DJANGO_HASH)

    assert credential["type"] == "password"
    assert json.loads(credential["credentialData"]) == {
        "hashIterations": 1000000,
        "algorithm": "pbkdf2-sha256",
        "additionalParameters": {},
    }
    secret = json.loads(credential["secretData"])
    assert secret["value"] == "aGFzaA=="
    assert base64.b64decode(secret["salt"]) == b"s4lt"


@pytest.mark.parametrize(
    "encoded",
    ["md5$salt$abc", "!unusable-password", "", None, "pbkdf2_sha256$broken"],
)
def test_hash_keycloak_cannot_take_gives_no_credential(encoded):
    assert credential_from_hash(encoded) is None


# --- one user ---


@pytest.mark.django_db
def test_push_creates_the_account_and_links_it(keycloak):
    user = User.objects.create_user(
        "olga", email="olga@example.com", first_name="Olga", last_name="Ivanova"
    )
    User.objects.filter(pk=user.pk).update(password=DJANGO_HASH)
    user.refresh_from_db()

    sub = push_user(user)

    account = keycloak.accounts["olga"]
    assert (account["email"], account["firstName"], account["enabled"]) == (
        "olga@example.com",
        "Olga",
        True,
    )
    assert account["credentials"] == [credential_from_hash(DJANGO_HASH)]
    assert KeycloakIdentity.objects.get(user=user).sub == sub == "kc-1"


@pytest.mark.django_db
def test_push_without_email_or_password(keycloak):
    user = User.objects.create_user("bare", is_active=False)

    push_user(user)

    account = keycloak.accounts["bare"]
    assert "email" not in account
    assert "credentials" not in account
    assert account["enabled"] is False


@pytest.mark.django_db
def test_push_of_a_taken_username_links_nothing(keycloak):
    keycloak.accounts["olga"] = {"id": "somebody-else"}
    user = User.objects.create_user("olga")

    with pytest.raises(KeycloakUserExists):
        push_user(user)
    assert not KeycloakIdentity.objects.exists()


@pytest.mark.django_db
def test_push_with_keycloak_down(keycloak):
    keycloak.down = True

    with pytest.raises(KeycloakUnavailable):
        push_user(User.objects.create_user("olga"))
    assert not KeycloakIdentity.objects.exists()


# --- creating a user in the panel with SSO on ---


def create_in_panel(client, admin, username="olga"):
    client.force_login(admin)
    return client.post(
        reverse("panel:user_create"),
        {
            "username": username,
            "password1": "Str0ng-Pass!2024",
            "password2": "Str0ng-Pass!2024",
        },
    )


@pytest.mark.django_db
def test_panel_user_gets_a_keycloak_account(client, group_admin, keycloak, settings):
    # The hasher of the real app; the test settings use a fast MD5 one.
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]

    response = create_in_panel(client, group_admin)

    assert response.status_code == 302
    user = User.objects.get(username="olga")
    assert user.keycloak_identity.sub == keycloak.accounts["olga"]["id"]
    assert keycloak.accounts["olga"]["credentials"] == [
        credential_from_hash(user.password)
    ]


@pytest.mark.django_db
def test_panel_creates_nobody_when_keycloak_is_down(client, group_admin, keycloak):
    keycloak.down = True

    response = create_in_panel(client, group_admin)

    assert response.status_code == 200
    assert "Keycloak is not available" in response.content.decode()
    assert not User.objects.filter(username="olga").exists()


@pytest.mark.django_db
def test_panel_refuses_a_username_keycloak_has(client, group_admin, keycloak):
    keycloak.accounts["olga"] = {"id": "somebody-else"}

    response = create_in_panel(client, group_admin)

    assert response.status_code == 200
    assert "Keycloak already has an account named olga" in response.content.decode()
    assert not User.objects.filter(username="olga").exists()


@pytest.mark.django_db
def test_panel_shows_why_keycloak_refused(client, group_admin, keycloak):
    keycloak.accounts["other"] = {"id": "kc-other", "email": "olga@example.com"}
    client.force_login(group_admin)

    response = client.post(
        reverse("panel:user_create"),
        {
            "username": "olga",
            "email": "olga@example.com",
            "password1": "Str0ng-Pass!2024",
            "password2": "Str0ng-Pass!2024",
        },
    )

    page = response.content.decode()
    assert "Keycloak refused the account: User exists with same email" in page
    assert not User.objects.filter(username="olga").exists()


@pytest.mark.django_db
def test_panel_without_sso_does_not_call_keycloak(client, group_admin):
    with patch("accounts.keycloak_admin.requests.post") as post:
        response = create_in_panel(client, group_admin)

    assert response.status_code == 302
    post.assert_not_called()


# --- switching SSO on: manage.py push_users_to_keycloak ---


def push_all():
    out = StringIO()
    call_command("push_users_to_keycloak", stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_command_pushes_users_without_an_account(keycloak, plain_user, group_admin):
    keycloak.accounts["boss"] = {"id": "made-by-hand"}

    out = push_all()

    assert "created in Keycloak: ivan" in out
    assert "not created in Keycloak: boss" in out
    assert "Created: 1, not created: 1." in out
    assert plain_user.keycloak_identity.sub == keycloak.accounts["ivan"]["id"]


@pytest.mark.django_db
def test_command_run_twice_creates_nothing_new(keycloak, plain_user):
    push_all()

    assert "Created: 0, not created: 0." in push_all()
    assert len(keycloak.accounts) == 1


@pytest.mark.django_db
def test_command_remakes_accounts_keycloak_lost(keycloak, plain_user, settings):
    """Development Keycloak started again from the realm file: accounts gone."""
    settings.KEYCLOAK_REMAKE_LOST_ACCOUNTS = True
    push_all()
    old_sub = plain_user.keycloak_identity.sub
    keycloak.accounts.clear()
    keycloak.accounts["someone"] = {"id": "kc-other"}

    out = push_all()

    assert "gone from Keycloak: ivan" in out
    assert "created in Keycloak: ivan" in out
    new_sub = KeycloakIdentity.objects.get(user=plain_user).sub
    assert new_sub != old_sub
    assert new_sub == keycloak.accounts["ivan"]["id"]


@pytest.mark.django_db
def test_command_leaves_a_deleted_account_deleted(keycloak, plain_user):
    """Production: an account missing in Keycloak was deleted on purpose."""
    push_all()
    sub = plain_user.keycloak_identity.sub
    keycloak.accounts.clear()

    out = push_all()

    assert "gone from Keycloak, left so: ivan" in out
    assert keycloak.accounts == {}
    assert KeycloakIdentity.objects.get(user=plain_user).sub == sub


@pytest.mark.django_db
def test_command_drops_a_lost_link_when_the_name_is_taken(
    keycloak, plain_user, settings
):
    """The realm file made the account again under a new id: link by name later."""
    settings.KEYCLOAK_REMAKE_LOST_ACCOUNTS = True
    push_all()
    keycloak.accounts = {"ivan": {"id": "kc-from-the-realm-file"}}

    out = push_all()

    assert "not created in Keycloak: ivan" in out
    assert not KeycloakIdentity.objects.exists()


@pytest.mark.django_db
def test_command_reports_a_taken_email(keycloak, plain_user):
    keycloak.accounts["other"] = {"id": "kc-other", "email": plain_user.email}

    out = push_all()

    assert "not created in Keycloak: ivan (User exists with same email)" in out


@pytest.mark.django_db
def test_one_token_serves_many_calls(keycloak, plain_user, group_admin):
    push_all()
    push_all()

    assert keycloak.tokens_given == 1


@pytest.mark.django_db
def test_command_stops_when_keycloak_is_down(keycloak, plain_user):
    keycloak.down = True

    with pytest.raises(CommandError, match="not available"):
        push_all()


@pytest.mark.django_db
def test_command_refuses_without_sso():
    with pytest.raises(CommandError, match="OIDC_ENABLED is off"):
        push_all()
