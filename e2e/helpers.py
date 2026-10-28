"""Small helpers shared by fixtures and tests."""

import uuid

import pytest
from playwright.sync_api import APIResponse, Page

import config
from config import User
from pages.keycloak_login_page import KeycloakLoginPage
from pages.login_page import LoginPage

# With SSO (E2E_AUTH=keycloak) these tests have nothing to check:
# tests/test_sso.py checks the same things on the Keycloak side.
local_sign_in_only = pytest.mark.skipif(
    config.SSO, reason="checks the app's own sign-in form, not used with SSO"
)

# CSRF_COOKIE_NAME of the app (config/settings.py): not Django's "csrftoken",
# so another Django app on the same host does not overwrite it.
CSRF_COOKIE = "users_roles_csrftoken"


def unique_name(prefix: str) -> str:
    """A name no other test run will use, for example "e2e_folder_3f9a1c2b".

    The app keeps everything the tests create, so every new user, folder or
    file gets a unique name. Then tests never collide with each other or with
    leftovers of an earlier run.
    """
    return f"e2e_{prefix}_{uuid.uuid4().hex[:8]}"


def sign_in(page: Page, user: User) -> Page:
    """Open /login/, sign in and wait until the app lets us in.

    With SSO /login/ leads to the Keycloak form, and after it Keycloak sends
    the browser back to the app.
    """
    if config.SSO:
        page.goto("/login/")
        KeycloakLoginPage(page).sign_in(user.username, user.password)
        # Keycloak -> /oidc/callback/ -> the page the app was asked for.
        page.wait_for_url(
            lambda url: not url.startswith(config.KEYCLOAK_URL) and "/oidc/" not in url
        )
        # The app refused the account: say so here, not as a timeout later.
        assert "/login/failed/" not in page.url, f"the app refused {user.username}"
        return page

    LoginPage(page).open().sign_in(user.username, user.password)
    # After a successful sign-in the app leaves /login/.
    page.wait_for_url(lambda url: "/login/" not in url)
    return page


def send_form(page: Page, path: str, data: dict) -> APIResponse:
    """Send a form straight to the server, without opening the page with it.

    This is how we check that the SERVER refuses an action, not only that the
    button is hidden. The request goes with the cookies of the signed-in user.

    Django refuses every form without a CSRF token, so we add the user's real
    token. Then a refusal can come only from the permission check.
    """
    cookies = page.context.cookies()
    csrf_token = next(
        (c.get("value") for c in cookies if c.get("name") == CSRF_COOKIE), None
    )
    assert csrf_token, f"no {CSRF_COOKIE} cookie: open a page with a form first"
    return page.request.post(path, form={"csrfmiddlewaretoken": csrf_token, **data})
