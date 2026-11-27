"""Results of a table file: /files/results/?path=...

Opens from the "Results" link next to a table file in the list. Shows what
Airflow computed for the file, or why there is nothing to show yet.
"""

from playwright.sync_api import Page

from pages.base_page import BasePage


class ResultsPage(BasePage):
    path = "/files/results/"

    def __init__(self, page: Page):
        super().__init__(page)
        # "Results: sales.csv"
        self.heading = page.get_by_role("heading", name="Results:")
        # One block per state; its data-state says which: unconfigured,
        # waiting, busy, failed or done.
        self.state = page.get_by_test_id("results-state")
        # "Grouped by device, sum(clicks)."
        self.rule = page.get_by_test_id("results-rule")
        self.choose_grouping_link = page.get_by_role("link", name="Choose the grouping")
        self.table = page.get_by_test_id("results-table")
        # "Download CSV": the whole result table as a file, only once done.
        self.download_link = page.get_by_test_id("results-download")
        self.back_link = page.get_by_role("link", name="Back to the folder")
