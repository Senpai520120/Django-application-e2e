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
