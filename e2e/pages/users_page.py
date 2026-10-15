"""User list of the admin panel: /manage/"""

from playwright.sync_api import Page

from pages.base_page import BasePage


class UsersPage(BasePage):
    path = "/manage/"

    def __init__(self, page: Page):
        super().__init__(page)
        self.heading = page.get_by_role("heading", name="Users")
        self.search_input = page.get_by_role("searchbox")
        self.search_button = page.get_by_role("button", name="Search")
        self.new_user_link = page.get_by_role("link", name="+ New user")
        self.nothing_found = page.get_by_text("Nothing found.")

    def search(self, text: str) -> None:
        self.search_input.fill(text)
        self.search_button.click()

    def row(self, username: str):
        """The table row of one user.

        We look for the row that has a cell with exactly this username,
        so "demo_user" does not also match "demo_user01".
        """
        return self.page.get_by_role("row").filter(
            has=self.page.get_by_role("cell", name=username, exact=True)
        )

    def role_badge(self, username: str, role: str):
        """A role name shown in the user's row, for example "admin"."""
        return self.row(username).get_by_text(role, exact=True)

    def open_roles_of(self, username: str) -> None:
        """Find the user and click "Roles" in their row."""
        self.search(username)
        self.row(username).get_by_role("link", name="Roles").click()

    def user_id(self, username: str) -> str:
        """The user's number in the database, read from their "Roles" link.

        The link looks like /manage/users/12/roles/, so the number is the
        fourth part when the address is split by "/".
        """
        self.search(username)
        link = self.row(username).get_by_role("link", name="Roles")
        href = link.get_attribute("href") or ""
        return href.split("/")[3]

    def deactivate_button(self, username: str):
        return self.row(username).get_by_role("button", name="Deactivate")

    def deactivate(self, username: str) -> None:
        """Click "Deactivate" in the user's row and wait for the server."""
        self.submit(self.deactivate_button(username))

    def activate_button(self, username: str):
        return self.row(username).get_by_role("button", name="Activate")
