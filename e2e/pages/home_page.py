"""Home page: / (who you are and which roles you hold)."""

from playwright.sync_api import Page

from pages.base_page import BasePage


class HomePage(BasePage):
    path = "/"

    def __init__(self, page: Page):
        super().__init__(page)
        # The heading reads "You are signed in as <username>".
        self.heading = page.get_by_role("heading", name="You are signed in as")

    def role_badge(self, role: str):
        """A role name in the "Your roles:" line, for example "user"."""
        return self.page.get_by_role("main").get_by_text(role, exact=True)
