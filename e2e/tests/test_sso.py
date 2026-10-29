"""Sign-in through Keycloak (SSO).

Runs only against the stack with docker-compose.sso.yml and E2E_AUTH=keycloak.
Keycloak answers "who you are"; roles and switching a user off stay in the
app's panel. These tests check both halves.
"""

import re
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Page, expect

import config
from helpers import sign_in, unique_name
from pages.home_page import HomePage
from pages.keycloak_login_page import KeycloakLoginPage
from pages.user_roles_page import UserRolesPage
from pages.users_page import UsersPage

pytestmark = pytest.mark.skipif(
    not config.SSO, reason="only with E2E_AUTH=keycloak (docker-compose.sso.yml)"
)

ACCESS_DENIED = "403 — access denied"


def test_44_anonymous_user_is_sent_to_keycloak_and_back(page: Page):
    """TC-44: an anonymous user goes to Keycloak and back to the page asked for."""
    page.goto("/files/")

    keycloak = KeycloakLoginPage(page)
    expect(page).to_have_url(keycloak.url_pattern)
    keycloak.sign_in(config.ADMIN.username, config.ADMIN.password)

    expect(page).to_have_url(re.compile(r"/files/$"))


def test_45_keycloak_session_signs_in_to_the_app(page: Page):
    """TC-45: whoever is signed in to Keycloak enters the app without the form (SSO)."""
    keycloak = KeycloakLoginPage(page).open_account_console()
    keycloak.sign_in(config.REGULAR_USER.username, config.REGULAR_USER.password)
    # The console works only with the realm's default roles; accounts from
    # the realm file get them only when the file names them.
    expect(keycloak.personal_info_heading).to_be_visible()

    page.goto("/")

    expect(HomePage(page).heading).to_have_text(
        f"You are signed in as {config.REGULAR_USER.username}"
    )


def test_46_sign_out_ends_the_keycloak_session(user_page: Page):
    """TC-46: signing out of the app signs out of Keycloak too (single logout)."""
    HomePage(user_page).open().sign_out()

    # Without the Keycloak session the form is back, not the app.
    keycloak = KeycloakLoginPage(user_page).open_account_console()
    expect(keycloak.sign_in_button).to_be_visible()
    user_page.goto("/")
    expect(keycloak.sign_in_button).to_be_visible()


def test_47_wrong_password_is_rejected_by_keycloak(page: Page):
    """TC-47: Keycloak refuses a wrong password and the app stays closed."""
    page.goto("/")
    keycloak = KeycloakLoginPage(page)

    keycloak.sign_in(config.REGULAR_USER.username, "wrong-password")

    expect(keycloak.error_message).to_be_visible()
    expect(page).to_have_url(keycloak.url_pattern)


def test_48_account_disabled_in_keycloak_cannot_sign_in(page: Page):
    """TC-48: an account switched off in Keycloak cannot sign in."""
    page.goto("/")
    keycloak = KeycloakLoginPage(page)

    keycloak.sign_in(config.KC_DISABLED.username, config.KC_DISABLED.password)

    expect(keycloak.account_disabled_message).to_be_visible()
    expect(page).to_have_url(keycloak.url_pattern)


def test_49_user_switched_off_in_the_panel_cannot_sign_in(page: Page):
    """TC-49: a user switched off in the panel stays out with a valid Keycloak password.

    demo_inactive is enabled in Keycloak and switched off in the app:
    the app, not Keycloak, decides who may come in.
    """
    page.goto("/")

    KeycloakLoginPage(page).sign_in(
        config.INACTIVE_USER.username, config.INACTIVE_USER.password
    )

    expect(page).to_have_url(re.compile(r"/login/failed/$"))
    expect(page.get_by_role("heading", name="Sign-in failed")).to_be_visible()
    # Keycloak still remembers the user, so the next try comes back to the
    # same page, not into the app and not round and round in a redirect loop.
    page.goto("/")
    expect(page).to_have_url(re.compile(r"/login/failed/$"))


def test_50_new_keycloak_user_gets_the_user_role(page: Page):
    """TC-50: someone who exists only in Keycloak comes in with the "user" role."""
    sign_in(page, config.KC_NEWCOMER)

    home_page = HomePage(page)
    expect(home_page.heading).to_have_text(
        f"You are signed in as {config.KC_NEWCOMER.username}"
    )
    expect(home_page.role_badge("user")).to_be_visible()
    response = page.goto("/manage/")
    assert response is not None and response.status == 403
    expect(page.get_by_text(ACCESS_DENIED)).to_be_visible()


@pytest.fixture
def promoted_user_page(page: Page, admin_browser: Page):
    """kc_promoted, signed in once, so the app knows them. Their admin
    role is taken back after the test, so the next run starts the same."""
    sign_in(page, config.KC_PROMOTED)

    yield page

    set_admin_role(admin_browser, config.KC_PROMOTED.username, False)


def set_admin_role(admin_browser: Page, username: str, on: bool) -> None:
    UsersPage(admin_browser).open().open_roles_of(username)
    roles_page = UserRolesPage(admin_browser)
    roles_page.role_checkbox("admin").set_checked(on)
    roles_page.save()


def test_51_role_given_in_the_panel_survives_the_next_sign_in(
    promoted_user_page: Page, admin_browser: Page
):
    """TC-51: the next sign-in through Keycloak keeps a role given in the panel."""
    set_admin_role(admin_browser, config.KC_PROMOTED.username, True)

    HomePage(promoted_user_page).open().sign_out()
    sign_in(promoted_user_page, config.KC_PROMOTED)

    expect(HomePage(promoted_user_page).open().role_badge("admin")).to_be_visible()
    response = promoted_user_page.goto("/manage/")
    assert response is not None and response.status == 200


def test_57_another_user_signs_in_after_sign_out(page: Page):
    """TC-57: after signing out, the next person signs in as themselves,
    not as the one before."""
    sign_in(page, config.REGULAR_USER)
    HomePage(page).open().sign_out()

    sign_in(page, config.ADMIN)

    home_page = HomePage(page).open()
    expect(home_page.heading).to_have_text(
        f"You are signed in as {config.ADMIN.username}"
    )
    expect(home_page.role_badge("admin")).to_be_visible()


def test_58_account_unknown_to_keycloak_cannot_sign_in(page: Page, admin_browser: Page):
    """TC-58: Keycloak refuses an account it does not have, and the app
    makes no user for it."""
    username = unique_name("nobody")
    page.goto("/")
    keycloak = KeycloakLoginPage(page)

    keycloak.sign_in(username, config.DEMO_PASSWORD)

    expect(keycloak.error_message).to_be_visible()
    expect(page).to_have_url(keycloak.url_pattern)
    users_page = UsersPage(admin_browser).open()
    users_page.search(username)
    expect(users_page.nothing_found).to_be_visible()


def test_59_cookies_of_another_app_on_localhost_do_not_break_sign_out(
    page: Page, base_url: str
):
    """TC-59: another Django app on localhost (AUTOforYOU) keeps its own
    csrftoken and sessionid there. Cookies are not kept apart by port, so
    they reach the app too. Sign-in and sign-out still work, and the other
    app's cookies stay as they were."""
    app_url = base_url.replace("127.0.0.1", "localhost")
    assert urlparse(app_url).hostname == "localhost", "the app must answer on localhost"

    def other_app_writes_cookies(value: str) -> None:
        page.context.add_cookies(
            [
                {"name": name, "value": value, "url": app_url}
                for name in ("csrftoken", "sessionid")
            ]
        )

    other_app_writes_cookies("a" * 32)
    page.goto(f"{app_url}/")
    KeycloakLoginPage(page).sign_in(
        config.REGULAR_USER.username, config.REGULAR_USER.password
    )
    home_page = HomePage(page)
    expect(home_page.heading).to_have_text(
        f"You are signed in as {config.REGULAR_USER.username}"
    )
    # The other app is used in another tab while ours stays open.
    other_app_writes_cookies("b" * 32)

    home_page.sign_out()

    expect(page.get_by_text("CSRF verification failed")).to_have_count(0)
    keycloak = KeycloakLoginPage(page)
    expect(page).to_have_url(keycloak.url_pattern)
    expect(keycloak.sign_in_button).to_be_visible()
    others = {
        c.get("name"): c.get("value")
        for c in page.context.cookies(app_url)
        if c.get("name") in ("csrftoken", "sessionid")
    }
    assert others == {"csrftoken": "b" * 32, "sessionid": "b" * 32}


def test_60_app_sign_in_opens_the_keycloak_account_console(user_page: Page):
    """TC-60: whoever signed in to the app enters Keycloak's account console
    without the form (SSO the other way round)."""
    keycloak = KeycloakLoginPage(user_page).open_account_console()

    expect(keycloak.personal_info_heading).to_be_visible()
    expect(keycloak.sign_in_button).to_have_count(0)
