"""Grouping of a table file: /files/grouping/?path=...

Opens by itself after a single table file is uploaded, or from the
"Grouping" link next to a table file in the list.
"""

from playwright.sync_api import Page

from pages.base_page import BasePage


class GroupingPage(BasePage):
    path = "/files/grouping/"

    def __init__(self, page: Page):
        super().__init__(page)
        # "Grouping: sales.csv"
        self.heading = page.get_by_role("heading", name="Grouping:")
        # One row per column of the file, in the file's order.
        self.columns = page.get_by_test_id("column")
        self.save_button = page.get_by_role("button", name="Save and process")
        self.error_messages = page.get_by_role("alert")

    def column_names(self) -> list[str]:
        return self.columns.evaluate_all("rows => rows.map(r => r.dataset.name)")

    def group_by(self, column: str):
        """The radio button that picks the column to group by."""
        return self.page.get_by_label(f"Group by {column}", exact=True)

    def aggregation(self, op: str, column: str):
        """The checkbox of one op for one column, for example sum of clicks.

        A text column has no checkbox for sum, avg, min and max at all.
        """
        return self.page.get_by_label(f"{op} of {column}", exact=True)

    def choose(self, group_by: str, *aggregations: tuple[str, str]) -> None:
        """Pick the column, tick the given (op, column) pairs and save.

        Boxes that are ticked but not listed are left as they are.
        """
        self.group_by(group_by).check()
        for op, column in aggregations:
            self.aggregation(op, column).check()
        self.submit(self.save_button)
