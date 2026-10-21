"""Sign-in through Keycloak: the user mapping and the logout address.

Keycloak itself is not needed: the backend is called with the claims
Keycloak would send, the way mozilla-django-oidc calls it after sign-in.
"""

from urllib.parse import parse_qs, urlsplit

import pytest
from django.test import override_settings
from django.urls import reverse

from accounts.oidc import KeycloakBackend, keycloak_logout_url
from accounts.views import LoginFailedView

OIDC_SETTINGS = {
    "OIDC_ENABLED": True,
    "OIDC_RP_CLIENT_ID": "django-app",
    "OIDC_RP_CLIENT_SECRET": "test-secret",
    "OIDC_RP_SIGN_ALGO": "RS256",
    "OIDC_OP_TOKEN_ENDPOINT": "http://kc/token",
    "OIDC_OP_USER_ENDPOINT": "http://kc/userinfo",
    "OIDC_OP_JWKS_ENDPOINT": "http://kc/certs",
    "OIDC_OP_LOGOUT_ENDPOINT": "http://kc/logout",
}


@pytest.fixture
def backend():
    with override_settings(**OIDC_SETTINGS):
        yield KeycloakBackend()


def claims(**extra):
    return {
        "preferred_username": "kc_ivan",
        "email": "ivan@example.com",
        "given_name": "Ivan",
        "family_name": "Petrov",
        **extra,
    }


def role_names(user):
    return list(user.groups.order_by("name").values_list("name", flat=True))


@pytest.mark.django_db
def test_new_user_gets_the_user_role_and_no_password(backend):
    user = backend.create_user(claims())

    assert user.username == "kc_ivan"
    assert (user.email, user.first_name, user.last_name) == (
        "ivan@example.com",
        "Ivan",
        "Petrov",
    )
    assert role_names(user) == ["user"]
    assert not user.has_usable_password()


@pytest.mark.django_db
def test_roles_in_the_token_are_ignored(backend):
    """Keycloak is not the source of roles: a role claim grants nothing."""
    user = backend.create_user(claims(roles=["admin"]))

    assert role_names(user) == ["user"]


@pytest.mark.django_db
def test_next_sign_in_keeps_roles_given_in_the_panel(backend, admin_group):
    user = backend.create_user(claims())
    user.groups.add(admin_group)

    backend.update_user(user, claims(email="new@example.com"))

    user.refresh_from_db()
    assert user.email == "new@example.com"
    assert role_names(user) == ["admin", "user"]


@pytest.mark.django_db
def test_existing_django_user_is_found_by_username(backend, plain_user):
    found = backend.filter_users_by_claims(claims(preferred_username="ivan"))

    assert list(found) == [plain_user]


@pytest.mark.django_db
def test_without_username_nobody_is_found(backend, plain_user):
    no_username = {"email": plain_user.email}

    assert not backend.filter_users_by_claims(no_username).exists()
    assert not backend.verify_claims(no_username)


@pytest.mark.django_db
def test_claims_with_username_are_accepted(backend):
    assert backend.verify_claims(claims())


@override_settings(**OIDC_SETTINGS)
def test_logout_url_ends_the_keycloak_session(rf):
    request = rf.get("/logout/")
    request.session = {"oidc_id_token": "the-id-token"}

    url = urlsplit(keycloak_logout_url(request))

    assert f"{url.scheme}://{url.netloc}{url.path}" == "http://kc/logout"
    assert parse_qs(url.query) == {
        "client_id": ["django-app"],
        "post_logout_redirect_uri": ["http://testserver/"],
        "id_token_hint": ["the-id-token"],
    }


@override_settings(**OIDC_SETTINGS)
def test_logout_url_without_id_token_has_no_hint(rf):
    request = rf.get("/logout/")
    request.session = {}

    assert "id_token_hint" not in keycloak_logout_url(request)


def test_login_failed_page_is_public(client):
    response = client.get(reverse("login_failed"))

    assert response.status_code == 200
    assert reverse("login") in response.content.decode()


@override_settings(**OIDC_SETTINGS)
def test_login_failed_page_offers_to_sign_out_of_keycloak(rf):
    # The view is called directly: the URLconf picks the sign-in mode once,
    # when first imported, and must not be loaded here with SSO switched on.
    request = rf.get("/login/failed/")
    request.session = {}

    response = LoginFailedView.as_view()(request)

    assert response.context_data["sso_logout_url"].startswith("http://kc/logout?")
