"""Signing in, signing out and the home page."""

import re

from playwright.sync_api import Page, expect

import config
from pages.files_page import FilesPage
from pages.home_page import HomePage
from pages.login_page import LoginPage


def test_01_anonymous_user_is_sent_to_sign_in(page: Page):
    """TC-01: an anonymous user who opens the home page is sent to sign in."""
    page.goto("/")

    expect(page).to_have_url(re.compile(r"/login/\?next=/$"))
    expect(LoginPage(page).heading).to_be_visible()


def test_02_user_signs_in_with_valid_credentials(page: Page):
    """TC-02: a user signs in and sees their name and role."""
    login_page = LoginPage(page).open()

    login_page.sign_in(config.REGULAR_USER.username, config.REGULAR_USER.password)

    home_page = HomePage(page)
    expect(home_page.heading).to_have_text("You are signed in as demo_user")
    expect(home_page.role_badge("user")).to_be_visible()


def test_03_wrong_password_is_rejected(page: Page):
    """TC-03: sign-in with a wrong password shows an error."""
    login_page = LoginPage(page).open()

    login_page.sign_in(config.REGULAR_USER.username, "wrong-password")

    expect(login_page.error_message).to_be_visible()
    expect(page).to_have_url(re.compile(r"/login/$"))


def test_04_unknown_username_gets_the_same_error(page: Page):
    """TC-04: an unknown username gets the same error as a wrong password.

    If the texts were different, an attacker could find out which usernames
    exist in the system.
    """
    login_page = LoginPage(page).open()

    login_page.sign_in(config.REGULAR_USER.username, "wrong-password")
    error_for_wrong_password = login_page.error_message.inner_text()

    login_page.sign_in("no_such_user_here", "wrong-password")
    error_for_unknown_user = login_page.error_message.inner_text()

    assert error_for_unknown_user == error_for_wrong_password


def test_05_deactivated_user_cannot_sign_in(page: Page):
    """TC-05: a switched-off user cannot sign in."""
    login_page = LoginPage(page).open()

    login_page.sign_in(config.INACTIVE_USER.username, config.INACTIVE_USER.password)

    expect(login_page.error_message).to_be_visible()
    expect(page).to_have_url(re.compile(r"/login/$"))


def test_06_user_signs_out(user_page: Page):
    """TC-06: after signing out the home page asks to sign in again."""
    home_page = HomePage(user_page).open()

    home_page.sign_out()
    user_page.goto("/")

    expect(user_page).to_have_url(re.compile(r"/login/\?next=/$"))


def test_07_header_link_opens_file_manager(user_page: Page):
    """TC-07: the "Files" link in the header opens the file manager."""
    home_page = HomePage(user_page).open()

    home_page.header_link("Files").click()

    expect(user_page).to_have_url(re.compile(r"/files/$"))
    expect(FilesPage(user_page).heading).to_be_visible()


def test_43_sign_in_does_not_send_user_to_another_site(page: Page):
    """TC-43: a link with ?next= pointing to another site does not take the user there.

    After sign-in the app goes to the address in ?next=. If it trusted any
    address, a fake link could send users to a lookalike site.
    """
    page.goto("/login/?next=https://evil.example/")

    LoginPage(page).sign_in(config.REGULAR_USER.username, config.REGULAR_USER.password)

    expect(HomePage(page).heading).to_be_visible()
    expect(page).not_to_have_url(re.compile("evil.example"))
