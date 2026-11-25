"""File manager: choosing how a table file is grouped.

After a table file is uploaded, the app shows its columns: pick the one to
group by and tick the math per group. Airflow is not part of these tests (the
CI stack runs without it); they check what the app shows and stores.

Every test works in its own folder from the `workspace` fixture.
"""

import pytest
from playwright.sync_api import expect

import config
from pages.files_page import FilesPage
from pages.grouping_page import GroupingPage

pytestmark = pytest.mark.skipif(
    not config.GROUPING, reason="the app under test has no PIPELINE_API_TOKEN"
)

SEO = (
    "query,device,clicks,impressions\n"
    "django,mobile,12,300\n"
    "django,desktop,9,150\n"
    "airflow,mobile,7,120\n"
)


def test_61_table_upload_opens_its_columns(files_page: FilesPage, workspace, make_file):
    """TC-61: a CSV upload opens the grouping page with its columns; no sum for text."""
    files_page.upload(make_file("seo.csv", SEO))

    grouping = GroupingPage(files_page.page)
    expect(grouping.heading).to_have_text("Grouping: seo.csv")
    expect(grouping.status_message).to_contain_text("Uploaded files: 1.")
    assert grouping.column_names() == ["query", "device", "clicks", "impressions"]
    # The first text column is the suggestion.
    expect(grouping.group_by("query")).to_be_checked()
    expect(grouping.aggregation("sum", "clicks")).to_be_visible()
    expect(grouping.aggregation("sum", "device")).to_have_count(0)
    expect(grouping.aggregation("count", "device")).to_be_visible()


def test_62_saved_grouping_shows_in_the_list_and_reopens(
    files_page: FilesPage, workspace, make_file
):
    """TC-62: the chosen column and math are confirmed, listed and shown again."""
    files_page.upload(make_file("seo.csv", SEO))

    GroupingPage(files_page.page).choose(
        "device", ("sum", "clicks"), ("avg", "impressions")
    )

    expect(files_page.status_message).to_contain_text(
        "seo.csv will be grouped by device with sum(clicks), avg(impressions)"
        " within a minute."
    )
    expect(files_page.grouping_status("seo.csv")).to_contain_text(
        "by device, sum(clicks), avg(impressions)"
    )
    files_page.submit(files_page.grouping_link("seo.csv"))
    grouping = GroupingPage(files_page.page)
    expect(grouping.group_by("device")).to_be_checked()
    expect(grouping.aggregation("sum", "clicks")).to_be_checked()
    expect(grouping.aggregation("avg", "impressions")).to_be_checked()
    expect(grouping.aggregation("max", "clicks")).not_to_be_checked()


def test_63_grouping_can_be_changed_later(files_page: FilesPage, workspace, make_file):
    """TC-63: the Grouping link changes the choice without uploading again."""
    files_page.upload(make_file("seo.csv", SEO))
    GroupingPage(files_page.page).choose("device", ("sum", "clicks"))

    files_page.submit(files_page.grouping_link("seo.csv"))
    grouping = GroupingPage(files_page.page)
    grouping.aggregation("sum", "clicks").uncheck()
    grouping.choose("query", ("max", "impressions"))

    expect(files_page.grouping_status("seo.csv")).to_have_text(
        "by query, max(impressions)"
    )


def test_64_other_files_and_several_tables(files_page: FilesPage, workspace, make_file):
    """TC-64: a text file has no grouping; several tables wait in the list."""
    files_page.upload(make_file("notes.txt", "hello"))
    expect(files_page.grouping_link("notes.txt")).to_have_count(0)

    files_page.upload(make_file("a.csv", SEO), make_file("b.csv", SEO))

    expect(files_page.status_message).to_contain_text("Grouping next to it")
    for name in ("a.csv", "b.csv"):
        expect(files_page.grouping_status(name)).to_contain_text(
            "waiting for a grouping column"
        )
        expect(files_page.grouping_link(name)).to_be_visible()
