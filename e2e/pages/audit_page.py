"""Audit log of role changes: /manage/audit/"""

from playwright.sync_api import Page

from pages.base_page import BasePage


class AuditPage(BasePage):
    path = "/manage/audit/"

    def __init__(self, page: Page):
        super().__init__(page)
        self.heading = page.get_by_role("heading", name="Audit: role changes")

        # The newest record is the first row of the table body.
        # get_by_role("rowgroup") finds <thead> and <tbody>; .last is <tbody>.
        self.newest_record = page.get_by_role("rowgroup").last.get_by_role("row").first

    def newest_record_cell(self, text: str):
        """A cell of the newest record with exactly this text."""
        return self.newest_record.get_by_role("cell", name=text, exact=True)
