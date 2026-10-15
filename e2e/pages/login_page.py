"""Sign-in page: /login/"""

from playwright.sync_api import Page

from pages.base_page import BasePage


class LoginPage(BasePage):
    path = "/login/"

    def __init__(self, page: Page):
        super().__init__(page)
        self.heading = page.get_by_role("heading", name="Sign in")
        self.username_input = page.get_by_label("Username")
        self.password_input = page.get_by_label("Password")
        self.sign_in_button = page.get_by_role("button", name="Sign in")
        # Django shows a failed sign-in as an item of an error list.
        self.error_message = page.get_by_role("listitem").filter(
            has_text="Please enter a correct username and password"
        )

    def sign_in(self, username: str, password: str) -> None:
        self.username_input.fill(username)
        self.password_input.fill(password)
        self.submit(self.sign_in_button)
