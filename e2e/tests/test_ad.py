"""Sign-in with Active Directory accounts, through Keycloak.

Runs only against the stack with docker-compose.ad.yml and E2E_AUTH=ad.
Keycloak reads AD (User Federation): AD decides who you are and checks the
password; roles stay in the app's panel. Each test adds its own person to AD
(directory.py), as the domain's administrator would, and removes them after.
"""

import pytest
from playwright.sync_api import Page, expect

import config
import directory
from config import User
from helpers import sign_in, unique_name
from pages.home_page import HomePage
from pages.keycloak_login_page import KeycloakLoginPage
from pages.user_create_page import UserCreatePage
from pages.users_page import UsersPage

pytestmark = pytest.mark.skipif(
    not config.AD, reason="only with E2E_AUTH=ad (docker-compose.ad.yml)"
)

AD_PASSWORD = "Ad-Pass-2024!"


@pytest.fixture
def ad_person():
    """Somebody who exists only in AD: not in Keycloak, not in the app."""
    # sAMAccountName holds at most 20 characters: e2e_ad_ + 8 = 15.
    username = unique_name("ad")
    email = f"{username}@{config.AD_EMAIL_DOMAIN}"
    directory.add_person(username, AD_PASSWORD, email=email)

    yield User(username, AD_PASSWORD), email

    directory.remove(username)


def test_52_ad_person_signs_in_with_the_ad_password(page: Page, ad_person):
    """TC-52: a person added to AD signs in with the AD password and gets "user"."""
    person, _ = ad_person

    sign_in(page, person)

    home_page = HomePage(page)
    expect(home_page.heading).to_have_text(f"You are signed in as {person.username}")
    expect(home_page.role_badge("user")).to_be_visible()
    response = page.goto("/manage/")
    assert response is not None and response.status == 403


def test_53_ad_person_signs_in_with_the_email(page: Page, ad_person):
    """TC-53: the AD email works as the username on the Keycloak form."""
    person, email = ad_person

    sign_in(page, User(email, person.password))

    expect(HomePage(page).heading).to_have_text(
        f"You are signed in as {person.username}"
    )


def test_54_account_switched_off_in_ad_cannot_sign_in(page: Page, ad_person):
    """TC-54: an account disabled in AD cannot sign in, with the right password."""
    person, _ = ad_person
    directory.switch_off(person.username)
    page.goto("/")
    keycloak = KeycloakLoginPage(page)

    keycloak.sign_in(person.username, person.password)

    # Keycloak says "Invalid username or password." for an AD account it has
    # not seen before, "Account is disabled" for one it has: out, either way.
    expect(
        keycloak.error_message.or_(keycloak.account_disabled_message)
    ).to_be_visible()
    expect(page).to_have_url(keycloak.url_pattern)


def test_55_password_set_in_ad_works_at_once(page: Page, ad_person):
    """TC-55: after a reset in AD the old password fails and the new one works."""
    person, _ = ad_person
    new_password = "Ad-Reset-2025!"
    directory.set_password(person.username, new_password)
    page.goto("/")
    keycloak = KeycloakLoginPage(page)

    keycloak.sign_in(person.username, person.password)
    expect(keycloak.error_message).to_be_visible()

    keycloak.sign_in(person.username, new_password)
    page.wait_for_url(lambda url: not url.startswith(config.KEYCLOAK_URL))
    expect(HomePage(page).heading).to_have_text(
        f"You are signed in as {person.username}"
    )


def test_56_user_made_in_the_panel_is_found_by_the_ad_email(
    page: Page, ad_person, admin_browser: Page, username_to_create: str
):
    """TC-56: a user made in the panel with a person's AD email is that person.

    The panel makes no Keycloak account for them; their AD sign-in, under
    another username, lands in the user made in the panel.
    """
    person, email = ad_person

    UserCreatePage(admin_browser).open().create_user(
        username_to_create, config.NEW_USER_PASSWORD, email=email
    )
    expect(UsersPage(admin_browser).status_message).to_contain_text(
        f"{username_to_create} is in Active Directory"
    )

    sign_in(page, person)

    expect(HomePage(page).heading).to_have_text(
        f"You are signed in as {username_to_create}"
    )
