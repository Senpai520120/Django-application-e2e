"""Form with the roles of one user: /manage/users/<id>/roles/

There is no fixed address: the page is opened from the user list
with UsersPage.open_roles_of().
"""

from playwright.sync_api import Page

from pages.base_page import BasePage


class UserRolesPage(BasePage):
    def __init__(self, page: Page):
        super().__init__(page)
        self.save_button = page.get_by_role("button", name="Save")
        self.cancel_link = page.get_by_role("link", name="Cancel")

    def heading(self, username: str):
        return self.page.get_by_role("heading", name=f"Roles of user {username}")

    def role_checkbox(self, role: str):
        """The checkbox of a role: "admin" or "user"."""
        return self.page.get_by_role("checkbox", name=role, exact=True)

    def save(self) -> None:
        self.submit(self.save_button)

    def role_id(self, role: str) -> str:
        """The role's number in the database: the value of its checkbox."""
        return self.role_checkbox(role).get_attribute("value") or ""

    def error_message(self, text: str):
        return self.page.get_by_text(text)
