"""Keycloak sign-in form: where /login/ leads when the app runs with SSO.

The page belongs to Keycloak, not to the app, so the locators are the ids
of its stock theme.
"""

import re

from playwright.sync_api import Page

import config
from pages.base_page import BasePage


class KeycloakLoginPage(BasePage):
    # Any page of the realm: the form itself has a one-time address.
    url_pattern = re.compile(re.escape(config.KEYCLOAK_URL) + "/")

    def __init__(self, page: Page):
        super().__init__(page)
        self.username_input = page.locator("#username")
        self.password_input = page.locator("#password")
        self.sign_in_button = page.locator("#kc-login")
        # Keycloak's message for a wrong password or an unknown username.
        self.error_message = page.get_by_text("Invalid username or password.")
        self.account_disabled_message = page.get_by_text("Account is disabled")

    def open_account_console(self):
        """The realm's own account page: signing in here signs in to Keycloak
        only, without passing through the app."""
        self.page.goto(f"{config.KEYCLOAK_URL}/account")
        return self

    def sign_in(self, username: str, password: str) -> None:
        self.username_input.fill(username)
        self.password_input.fill(password)
        self.submit(self.sign_in_button)
