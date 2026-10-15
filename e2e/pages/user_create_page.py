"""Form for a new user: /manage/users/new/"""

from playwright.sync_api import Page

from pages.base_page import BasePage


class UserCreatePage(BasePage):
    path = "/manage/users/new/"

    def __init__(self, page: Page):
        super().__init__(page)
        self.heading = page.get_by_role("heading", name="New user")
        self.username_input = page.get_by_label("Username")
        # exact=True: without it "Password" would also match "Password confirmation".
        self.password_input = page.get_by_label("Password:", exact=True)
        self.password_confirmation_input = page.get_by_label("Password confirmation")
        self.create_button = page.get_by_role("button", name="Create")

    def create_user(self, username: str, password: str) -> None:
        self.username_input.fill(username)
        self.password_input.fill(password)
        self.password_confirmation_input.fill(password)
        self.submit(self.create_button)
