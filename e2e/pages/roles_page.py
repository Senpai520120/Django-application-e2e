"""Roles and how many users hold each: /manage/roles/"""

from playwright.sync_api import Page

from pages.base_page import BasePage


class RolesPage(BasePage):
    path = "/manage/roles/"

    def __init__(self, page: Page):
        super().__init__(page)
        self.heading = page.get_by_role("heading", name="Roles", exact=True)

    def members_count_cell(self, role: str):
        """The "Users" cell in the row of a role: the last cell of that row."""
        role_row = self.page.get_by_role("row").filter(
            has=self.page.get_by_role("cell", name=role, exact=True)
        )
        return role_row.get_by_role("cell").last

    def members_count(self, role: str) -> int:
        return int(self.members_count_cell(role).inner_text())
