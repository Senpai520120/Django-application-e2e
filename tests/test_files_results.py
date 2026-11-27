"""The Results page of a table file, read from a real DuckDB file.

The DuckDB file is written by the DAG's own save_groups and mark_failed, so
the page is tested against exactly what Airflow writes.
"""

import subprocess
import sys

import duckdb
import pytest
from django.urls import reverse
from upload_groups import mark_failed, save_groups

from files import results
from files.models import GroupingRule

TOKEN = "pipeline-token"
SALES = "category,amount\nbooks,10\ntoys,5\nbooks,7\n"


@pytest.fixture
def file_root(tmp_path, settings):
    settings.STORAGES = {
        **settings.STORAGES,
        "filemanager": {
            "BACKEND": "files.storage.LocalFileStorage",
            "OPTIONS": {"location": str(tmp_path / "storage")},
        },
    }
    root = tmp_path / "storage"
    root.mkdir()
    (root / "sales.csv").write_text(SALES)
    (root / "notes.txt").write_text("hello")
    return root


@pytest.fixture
def db(tmp_path, settings):
    """Where Airflow's DuckDB file would be; nothing is written there yet."""
    settings.PIPELINE_API_TOKEN = TOKEN
    settings.DUCKDB_PATH = str(tmp_path / "analytics.duckdb")
    return tmp_path / "analytics.duckdb"


@pytest.fixture
def user_client(client, plain_user, file_root):
    client.force_login(plain_user)
    return client


def configured(path="sales.csv", **fields):
    return GroupingRule.objects.create(
        path=path,
        group_by="category",
        aggregations=[{"op": "sum", "column": "amount"}],
        configured=True,
        revision=1,
        **fields,
    )


def process(db, rule, source_file, **overrides):
    """What group_file does for `rule`: the result table and the done mark."""
    options = {
        "rule_id": rule.pk,
        "mtime_ms": 1,
        "group_by": rule.group_by,
        "aggregations": rule.aggregations,
        "revision": rule.revision,
        **overrides,
    }
    save_groups(db, source_file, rule.path, rule.group_by, **options)


def page(client, path="sales.csv"):
    return client.get(reverse("files:results"), {"path": path})


def state(response):
    return response.context["result"].state if response.context["result"] else None


@pytest.mark.django_db
def test_anonymous_is_sent_to_sign_in(client, file_root, db):
    response = page(client)

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


@pytest.mark.django_db
@pytest.mark.parametrize("off", ["PIPELINE_API_TOKEN", "DUCKDB_PATH"])
def test_page_is_off_without_the_pipeline(user_client, db, settings, off):
    setattr(settings, off, "")

    assert page(user_client).status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["", "notes.txt", "missing.csv", "../sales.csv"])
def test_only_existing_table_files_have_results(user_client, db, path):
    assert page(user_client, path).status_code in (400, 404)


@pytest.mark.django_db
@pytest.mark.parametrize("draft", [True, False])
def test_no_rule_or_a_draft_asks_for_a_grouping(user_client, db, draft):
    if draft:
        GroupingRule.objects.create(path="sales.csv")

    response = page(user_client)

    assert response.status_code == 200
    assert state(response) is None
    content = response.content.decode()
    assert "Choose a grouping first" in content
    assert reverse("files:grouping") + "?path=sales.csv" in content


@pytest.mark.django_db
def test_saved_rule_waits_for_airflow(user_client, db):
    configured()

    response = page(user_client)

    # No DuckDB file at all yet.
    assert state(response) == "waiting"
    assert "Not processed yet" in response.content.decode()


@pytest.mark.django_db
def test_done_file_shows_its_table(user_client, db, file_root):
    rule = configured()
    process(db, rule, file_root / "sales.csv")

    response = page(user_client)

    assert state(response) == "done"
    result = response.context["result"]
    assert result.columns == ["category", "row_count", "sum_amount"]
    assert result.rows == [("books", 2, 17), ("toys", 1, 5)]
    content = response.content.decode()
    assert '<th scope="col">sum_amount</th>' in content
    assert "Groups: 2." in content
    assert "Only the first" not in content


@pytest.mark.django_db
def test_result_of_an_older_rule_is_not_shown(user_client, db, file_root):
    rule = configured()
    process(db, rule, file_root / "sales.csv")
    # Saved again with other math: Airflow has not caught up yet.
    rule.revision = 2
    rule.save()

    assert state(page(user_client)) == "waiting"


@pytest.mark.django_db
def test_result_of_a_deleted_file_with_the_same_name_is_not_shown(
    user_client, db, file_root
):
    old = configured()
    process(db, old, file_root / "sales.csv")
    old.delete()
    configured()

    assert state(page(user_client)) == "waiting"


@pytest.mark.django_db
def test_failed_file_shows_the_error(user_client, db):
    rule = configured()
    mark_failed(db, "sales.csv", 1, "category", [], "No column 'price'", 1, rule.pk)

    response = page(user_client)

    assert state(response) == "failed"
    assert "No column &#x27;price&#x27;" in response.content.decode()


@pytest.mark.django_db
def test_dates_show_as_duckdb_has_them(user_client, db, file_root):
    (file_root / "days.csv").write_text(
        "day,seen\n2026-11-01,2026-11-01 09:30:00\n2026-11-01,2026-11-01 18:05:00\n"
    )
    rule = configured("days.csv")
    rule.group_by = "day"
    rule.aggregations = [{"op": "max", "column": "seen"}]
    rule.save()
    process(db, rule, file_root / "days.csv")

    content = page(user_client, "days.csv").content.decode()

    # Not "Nov. 1, 2026": the page shows what SQL over the table gives.
    assert "<td>2026-11-01</td>" in content
    assert "<td>2026-11-01 18:05:00</td>" in content


@pytest.mark.django_db
def test_values_from_the_file_are_escaped(user_client, db, file_root):
    (file_root / "evil.csv").write_text(
        "category,amount\n<script>alert(1)</script>,1\n,2\n"
    )
    rule = configured(
        "evil.csv",
    )
    process(db, rule, file_root / "evil.csv")

    content = page(user_client, "evil.csv").content.decode()

    assert "<script>alert(1)</script>" not in content
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in content
    # An empty group shows as a dash, last.
    assert "<td>—</td>" in content


@pytest.mark.django_db
def test_long_results_are_cut_and_say_so(user_client, db, file_root, monkeypatch):
    monkeypatch.setattr(results, "MAX_ROWS", 2)
    monkeypatch.setattr("files.views.MAX_ROWS", 2)
    (file_root / "many.csv").write_text(
        "category,amount\n" + "".join(f"c{n},1\n" for n in range(5))
    )
    rule = configured("many.csv")
    process(db, rule, file_root / "many.csv")

    response = page(user_client, "many.csv")

    assert len(response.context["result"].rows) == 2
    content = response.content.decode()
    assert "Groups: 5." in content
    assert "Only the first 2 are shown." in content


@pytest.mark.django_db
def test_database_from_before_rule_ids_waits(user_client, db):
    configured()
    with duckdb.connect(str(db)) as con:
        con.execute("CREATE TABLE processed_files (source VARCHAR, status VARCHAR)")

    assert state(page(user_client)) == "waiting"


@pytest.mark.django_db
def test_empty_database_waits(user_client, db):
    configured()
    duckdb.connect(str(db)).close()

    assert state(page(user_client)) == "waiting"


@pytest.mark.django_db
def test_done_row_without_its_table_waits(user_client, db, file_root):
    rule = configured()
    process(db, rule, file_root / "sales.csv")
    with duckdb.connect(str(db)) as con:
        con.execute(f"DROP TABLE result_{rule.pk}")

    assert state(page(user_client)) == "waiting"


HOLD_THE_WRITE_LOCK = """
import sys, duckdb
con = duckdb.connect(sys.argv[1])
print("locked", flush=True)
sys.stdin.read()
"""


@pytest.mark.django_db
def test_file_locked_by_airflow_asks_to_refresh(user_client, db, file_root):
    rule = configured()
    process(db, rule, file_root / "sales.csv")
    # A real second process, as Airflow is: DuckDB locks the file per process.
    writer = subprocess.Popen(
        [sys.executable, "-c", HOLD_THE_WRITE_LOCK, str(db)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert writer.stdout.readline().strip() == "locked"

        response = page(user_client)
    finally:
        writer.communicate("")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert "Refresh the page in a few seconds" in response.content.decode()


@pytest.mark.django_db
def test_other_database_errors_are_not_hidden(user_client, db, monkeypatch):
    configured()
    db.write_text("")

    def broken(*args, **kwargs):
        raise duckdb.IOException("Permission denied")

    monkeypatch.setattr("files.results.duckdb.connect", broken)

    with pytest.raises(duckdb.IOException):
        page(user_client)


@pytest.mark.django_db
def test_list_links_to_the_results(user_client, db):
    content = user_client.get(reverse("files:browse")).content.decode()

    assert 'aria-label="Results sales.csv"' in content
    assert 'aria-label="Results notes.txt"' not in content


@pytest.mark.django_db
def test_list_has_no_results_link_without_duckdb(user_client, db, settings):
    settings.DUCKDB_PATH = ""

    content = user_client.get(reverse("files:browse")).content.decode()

    assert "Grouping sales.csv" in content
    assert "Results sales.csv" not in content


# The whole result as a CSV file (Download CSV on the Results page).


def download(client, path="sales.csv"):
    return client.get(reverse("files:results_download"), {"path": path})


def csv_rows(response):
    import csv

    text = response.content.decode("utf-8-sig")
    return list(csv.reader(text.splitlines()))


@pytest.mark.django_db
def test_download_gives_every_group_as_csv(user_client, db, file_root, monkeypatch):
    # The page cuts at MAX_ROWS; the file never does.
    monkeypatch.setattr(results, "MAX_ROWS", 2)
    monkeypatch.setattr("files.views.MAX_ROWS", 2)
    (file_root / "many.csv").write_text(
        "category,amount\n" + "".join(f"c{n},{n}\n" for n in range(5))
    )
    rule = configured("many.csv")
    process(db, rule, file_root / "many.csv")

    response = download(user_client, "many.csv")

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    assert response["Content-Disposition"] == ('attachment; filename="many_result.csv"')
    # A BOM first, so Excel reads non-Latin text right.
    assert response.content.startswith("﻿".encode())
    assert csv_rows(response) == [
        ["category", "row_count", "sum_amount"],
        *[[f"c{n}", "1", str(n)] for n in range(5)],
    ]


@pytest.mark.django_db
def test_download_link_is_on_the_page_of_a_result(user_client, db, file_root):
    rule = configured()
    process(db, rule, file_root / "sales.csv")

    content = page(user_client).content.decode()

    assert reverse("files:results_download") + "?path=sales.csv" in content
    assert "Download CSV" in content


@pytest.mark.django_db
def test_no_download_link_while_waiting(user_client, db):
    configured()

    assert "Download CSV" not in page(user_client).content.decode()


@pytest.mark.django_db
def test_download_keeps_values_as_they_are_stored(user_client, db, file_root):
    (file_root / "days.csv").write_text(
        'day,amount,note\n2026-11-01,-3,=HYPERLINK("http://x")\n'
        "2026-11-02,4,\n,5,@sum\n"
    )
    rule = configured("days.csv")
    rule.group_by = "day"
    rule.aggregations = [
        {"op": "sum", "column": "amount"},
        {"op": "max", "column": "note"},
    ]
    rule.save()
    process(db, rule, file_root / "days.csv")

    rows = csv_rows(download(user_client, "days.csv"))

    assert rows == [
        ["day", "row_count", "sum_amount", "max_note"],
        # A negative sum stays a number; text that a spreadsheet would run as
        # a formula gets an apostrophe; NULL is an empty cell; dates are ISO.
        ["2026-11-01", "1", "-3", '\'=HYPERLINK("http://x")'],
        ["2026-11-02", "1", "4", ""],
        ["", "1", "5", "'@sum"],
    ]


@pytest.mark.django_db
def test_download_names_a_non_latin_file(user_client, db, file_root):
    (file_root / "продажі.csv").write_text(SALES)
    rule = configured("продажі.csv")
    process(db, rule, file_root / "продажі.csv")

    response = download(user_client, "продажі.csv")

    assert response.status_code == 200
    assert "filename*=utf-8''" in response["Content-Disposition"]


@pytest.mark.django_db
@pytest.mark.parametrize("draft", [True, False])
def test_no_download_without_a_saved_grouping(user_client, db, draft):
    if draft:
        GroupingRule.objects.create(path="sales.csv")

    assert download(user_client).status_code == 404


@pytest.mark.django_db
def test_no_download_before_airflow_or_after_a_failure(user_client, db):
    rule = configured()
    assert download(user_client).status_code == 404

    mark_failed(db, "sales.csv", 1, "category", [], "No column 'price'", 1, rule.pk)
    assert download(user_client).status_code == 404


@pytest.mark.django_db
def test_download_while_airflow_writes_asks_to_retry(user_client, db, monkeypatch):
    configured()
    monkeypatch.setattr(
        "files.views.read_result", lambda rule, everything: results.Result("busy")
    )

    response = download(user_client)

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["", "notes.txt", "missing.csv", "../sales.csv"])
def test_download_only_for_existing_table_files(user_client, db, path):
    assert download(user_client, path).status_code in (400, 404)


@pytest.mark.django_db
def test_download_needs_sign_in(client, file_root, db):
    response = download(client)

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


@pytest.mark.django_db
def test_no_download_without_the_pipeline(user_client, db, settings):
    settings.DUCKDB_PATH = ""

    assert download(user_client).status_code == 404
