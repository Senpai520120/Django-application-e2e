"""File manager: the Results page of a table file.

Airflow is not part of these tests (the CI stack runs without it), so they
check the states the app shows before Airflow has written anything: nothing
chosen yet, and chosen but not processed. The table itself is tested in the
app's unit tests against a real DuckDB file.

Every test works in its own folder from the `workspace` fixture.
"""

import re

import pytest
from playwright.sync_api import expect

import config
from pages.files_page import FilesPage
from pages.grouping_page import GroupingPage
from pages.results_page import ResultsPage

pytestmark = pytest.mark.skipif(
    not config.RESULTS, reason="the app under test has no DUCKDB_PATH"
)

SEO = "query,device,clicks\ndjango,mobile,12\ndjango,desktop,9\nairflow,mobile,7\n"


def open_results(files_page: FilesPage, name: str) -> ResultsPage:
    files_page.submit(files_page.results_link(name))
    return ResultsPage(files_page.page)


def test_65_results_ask_for_a_grouping_first(
    files_page: FilesPage, workspace, make_file
):
    """TC-65: a table file with no grouping chosen points to the grouping page."""
    files_page.upload(make_file("a.csv", SEO), make_file("b.csv", SEO))

    results = open_results(files_page, "a.csv")

    expect(results.heading).to_have_text("Results: a.csv")
    expect(results.state).to_have_attribute("data-state", "unconfigured")
    expect(results.state).to_contain_text("Choose a grouping first")
    results.submit(results.choose_grouping_link)
    expect(GroupingPage(files_page.page).heading).to_have_text("Grouping: a.csv")


def test_66_saved_grouping_waits_for_airflow(
    files_page: FilesPage, workspace, make_file
):
    """TC-66: after Save the page names the grouping and waits for Airflow."""
    files_page.upload(make_file("seo.csv", SEO))
    GroupingPage(files_page.page).choose("device", ("sum", "clicks"))

    results = open_results(files_page, "seo.csv")

    expect(results.rule).to_contain_text("Grouped by device, sum(clicks).")
    # With Airflow running (the local stand) it may already be done; in CI
    # there is no Airflow, and the page waits.
    expect(results.state).to_have_attribute("data-state", re.compile("waiting|done"))
    results.submit(results.back_link)
    expect(files_page.entry("seo.csv")).to_be_visible()


def test_67_only_table_files_have_results(files_page: FilesPage, workspace, make_file):
    """TC-67: a text file has no Results link."""
    files_page.upload(make_file("notes.txt", "hello"))

    expect(files_page.results_link("notes.txt")).to_have_count(0)
