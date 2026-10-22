"""Sign-in through Keycloak: the user mapping and the logout address.

Keycloak itself is not needed. Each test plays the part of mozilla-django-oidc
after a sign-in: it hands the backend the claims Keycloak would send and calls
get_or_create_user, the same chain verify -> find -> update or create.
"""

from io import StringIO
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.core.management import CommandError, call_command
from django.db import IntegrityError
from django.test import override_settings
from django.urls import reverse
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from accounts.models import KeycloakIdentity
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
    "OIDC_POST_LOGOUT_REDIRECT_URL": "",
}


@pytest.fixture
def backend():
    with override_settings(**OIDC_SETTINGS):
        yield KeycloakBackend()


def claims(**extra):
    return {
        "sub": "sub-ivan",
        "preferred_username": "kc_ivan",
        "email": "ivan@example.com",
        "given_name": "Ivan",
        "family_name": "Petrov",
        **extra,
    }


def sign_in(backend, user_claims, id_token_sub=None):
    """What happens after Keycloak sends the user back: claims -> Django user.

    Only the HTTP call for userinfo is replaced, so the backend's own check
    of userinfo against the signed id token still runs.
    """
    payload = {"sub": id_token_sub or user_claims.get("sub")}
    with patch.object(
        OIDCAuthenticationBackend, "get_userinfo", return_value=user_claims
    ):
        return backend.get_or_create_user("access-token", "id-token", payload)


def role_names(user):
    return list(user.groups.order_by("name").values_list("name", flat=True))


# --- a new user ---


@pytest.mark.django_db
def test_new_user_gets_the_user_role_and_no_password(backend):
    user = sign_in(backend, claims())

    assert user.username == "kc_ivan"
    assert (user.email, user.first_name, user.last_name) == (
        "ivan@example.com",
        "Ivan",
        "Petrov",
    )
    assert role_names(user) == ["user"]
    assert not user.has_usable_password()
    assert user.keycloak_identity.sub == "sub-ivan"


@pytest.mark.django_db
def test_roles_in_the_token_are_ignored(backend):
    """Keycloak is not the source of roles: a role claim grants nothing."""
    user = sign_in(backend, claims(roles=["admin"]))

    assert role_names(user) == ["user"]


@pytest.mark.django_db
def test_user_without_email_comes_in(backend):
    user_claims = claims()
    del user_claims["email"]

    user = sign_in(backend, user_claims)

    assert user.username == "kc_ivan"
    assert user.email == ""


@pytest.mark.django_db
def test_missing_user_group_is_created_not_a_crash(backend):
    Group.objects.filter(name="user").delete()

    user = sign_in(backend, claims())

    assert role_names(user) == ["user"]


@pytest.mark.django_db
def test_names_longer_than_the_columns_are_cut(backend):
    user = sign_in(backend, claims(given_name="A" * 255, family_name="B" * 255))

    user.refresh_from_db()
    assert user.first_name == "A" * 150
    assert user.last_name == "B" * 150


@pytest.mark.parametrize("missing", ["sub", "preferred_username"])
@pytest.mark.django_db
def test_claims_without_id_or_username_are_refused(backend, missing):
    user_claims = claims()
    del user_claims[missing]

    with pytest.raises(PermissionDenied):
        sign_in(backend, user_claims)
    assert not User.objects.filter(username="kc_ivan").exists()


# --- the next sign-in ---


@pytest.mark.django_db
def test_next_sign_in_keeps_roles_given_in_the_panel(backend, admin_group):
    user = sign_in(backend, claims())
    user.groups.add(admin_group)

    again = sign_in(backend, claims(email="new@example.com"))

    assert again == user
    again.refresh_from_db()
    assert again.email == "new@example.com"
    assert role_names(again) == ["admin", "user"]


@pytest.mark.django_db
def test_renamed_keycloak_account_is_still_the_same_user(backend):
    user = sign_in(backend, claims())

    again = sign_in(backend, claims(preferred_username="kc_ivan_renamed"))

    assert again == user
    assert User.objects.count() == 1


# --- linking an account the app already has ---


@pytest.mark.django_db
def test_existing_user_is_linked_on_the_first_sign_in(backend, plain_user):
    user = sign_in(backend, claims(preferred_username="ivan"))

    assert user == plain_user
    assert KeycloakIdentity.objects.get(user=plain_user).sub == "sub-ivan"


@pytest.mark.django_db
def test_existing_user_is_found_whatever_the_case(backend, plain_user):
    """Keycloak lowercases usernames; the Django one may have capitals."""
    User.objects.filter(pk=plain_user.pk).update(username="Ivan")

    user = sign_in(backend, claims(preferred_username="ivan"))

    assert user == plain_user


@pytest.mark.django_db
def test_another_keycloak_account_cannot_take_a_linked_user(backend, plain_user):
    sign_in(backend, claims(preferred_username="ivan"))

    with pytest.raises(PermissionDenied):
        sign_in(backend, claims(sub="sub-intruder", preferred_username="ivan"))
    assert KeycloakIdentity.objects.get(user=plain_user).sub == "sub-ivan"


@pytest.mark.parametrize("flag", ["is_staff", "is_superuser"])
@pytest.mark.django_db
def test_account_with_admin_site_access_is_not_linked_by_name(backend, flag):
    User.objects.create_user("root", **{flag: True})

    with pytest.raises(PermissionDenied):
        sign_in(backend, claims(preferred_username="root"))
    assert not KeycloakIdentity.objects.exists()


@pytest.mark.django_db
def test_panel_admin_is_not_linked_by_name(backend, group_admin):
    """An admin of the panel (admin group) is linked only by hand."""
    with pytest.raises(PermissionDenied):
        sign_in(backend, claims(preferred_username="boss"))
    assert not KeycloakIdentity.objects.exists()


@pytest.mark.django_db
def test_exact_spelling_wins_over_other_case(backend, plain_user):
    other = User.objects.create_user("Ivan")

    user = sign_in(backend, claims(preferred_username="Ivan"))

    assert user == other


@pytest.mark.django_db
def test_two_users_differing_only_in_case_are_not_guessed(backend):
    User.objects.create_user("IVAN")
    User.objects.create_user("Ivan")

    with pytest.raises(PermissionDenied):
        sign_in(backend, claims(preferred_username="ivan"))
    assert not KeycloakIdentity.objects.exists()


# --- refusals that must not turn into errors ---


@pytest.mark.django_db
def test_username_longer_than_the_column_is_refused(backend):
    with pytest.raises(PermissionDenied):
        sign_in(backend, claims(preferred_username="a" * 151))
    assert not User.objects.exists()


@pytest.mark.django_db
def test_userinfo_of_another_account_is_refused(backend):
    """userinfo must be about the account the signed id token names."""
    with pytest.raises(PermissionDenied):
        sign_in(backend, claims(), id_token_sub="sub-somebody-else")
    assert not KeycloakIdentity.objects.exists()


@pytest.mark.django_db
def test_same_first_sign_in_twice_at_once_is_refused_not_a_crash(backend):
    with (
        patch.object(User.objects, "create_user", side_effect=IntegrityError),
        pytest.raises(PermissionDenied),
    ):
        sign_in(backend, claims())


@pytest.mark.django_db
def test_email_too_long_is_dropped_not_cut(backend):
    long_email = "a" * 250 + "@example.com"

    user = sign_in(backend, claims(email=long_email))

    user.refresh_from_db()
    assert user.email == ""


# --- the session of a user switched off in the panel ---


@pytest.mark.django_db
def test_switched_off_user_loses_the_session(backend):
    user = sign_in(backend, claims())
    assert backend.get_user(user.pk) == user

    User.objects.filter(pk=user.pk).update(is_active=False)

    assert backend.get_user(user.pk) is None


@pytest.mark.django_db
def test_unknown_session_user_is_nobody(backend):
    assert backend.get_user(999999) is None


# --- linking by hand: manage.py link_keycloak_user ---


def link(*args):
    out = StringIO()
    call_command("link_keycloak_user", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_command_links_an_admin_who_then_signs_in(backend, group_admin):
    assert "boss = sub-boss" in link("boss=sub-boss")

    user = sign_in(backend, claims(sub="sub-boss", preferred_username="boss"))

    assert user == group_admin


@pytest.mark.django_db
def test_command_does_not_move_a_link_without_replace(group_admin):
    link("boss=sub-old")

    with pytest.raises(CommandError, match="--replace"):
        link("boss=sub-new")
    assert group_admin.keycloak_identity.sub == "sub-old"


@pytest.mark.django_db
def test_command_moves_a_link_with_replace(group_admin):
    link("boss=sub-old")

    link("--replace", "boss=sub-new")

    assert KeycloakIdentity.objects.get().sub == "sub-new"


@pytest.mark.django_db
def test_command_repeated_with_replace_changes_nothing(group_admin):
    link("--replace", "boss=sub-boss")
    link("--replace", "boss=sub-boss")

    assert KeycloakIdentity.objects.get().sub == "sub-boss"


@pytest.mark.parametrize("bad", ["boss", "boss=", "=sub", "nobody=sub"])
@pytest.mark.django_db
def test_command_refuses_bad_input(group_admin, bad):
    with pytest.raises(CommandError):
        link(bad)
    assert not KeycloakIdentity.objects.exists()


# --- signing out ---


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


@override_settings(
    **{**OIDC_SETTINGS, "OIDC_POST_LOGOUT_REDIRECT_URL": "https://app.example/"}
)
def test_logout_url_uses_the_configured_return_address(rf):
    request = rf.get("/logout/")
    request.session = {}

    query = parse_qs(urlsplit(keycloak_logout_url(request)).query)

    assert query["post_logout_redirect_uri"] == ["https://app.example/"]


# --- the sign-in failed page ---


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
