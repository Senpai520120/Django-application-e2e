"""The DAG's grouping, run against a real DuckDB file."""

import duckdb
import pytest
from upload_groups import (
    UploadError,
    file_columns,
    pick_column,
    resolve_upload,
    save_groups,
)

SALES = "category,amount\nbooks,10\ntoys,5\nbooks,7\n"


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "filestore"
    (root / "reports").mkdir(parents=True)
    (root / "reports" / "sales.csv").write_text(SALES)
    return root


def rows(db_path):
    with duckdb.connect(str(db_path)) as con:
        return con.execute(
            "SELECT source, group_column, group_value, row_count"
            " FROM upload_groups ORDER BY group_value"
        ).fetchall()


def test_groups_by_the_first_column(store, tmp_path):
    path = resolve_upload(store, "reports/sales.csv")
    column = pick_column(file_columns(path), None)

    db = tmp_path / "a.duckdb"

    assert save_groups(db, path, "reports/sales.csv", column) == 2
    assert rows(db) == [
        ("reports/sales.csv", "category", "books", 2),
        ("reports/sales.csv", "category", "toys", 1),
    ]


def test_same_file_again_replaces_its_groups(store, tmp_path):
    db = tmp_path / "a.duckdb"
    path = resolve_upload(store, "reports/sales.csv")

    save_groups(db, path, "reports/sales.csv", "category")
    save_groups(db, path, "reports/sales.csv", "category")

    assert len(rows(db)) == 2


def test_requested_column_must_exist(store):
    columns = file_columns(resolve_upload(store, "reports/sales.csv"))

    assert pick_column(columns, "amount") == "amount"
    with pytest.raises(UploadError):
        pick_column(columns, "price")


@pytest.fixture(scope="module")
def table_files(tmp_path_factory):
    """The same sales table saved in every format the DAG reads."""
    folder = tmp_path_factory.mktemp("tables")
    with duckdb.connect() as con:
        # Writing .xlsx needs the excel extension loaded; reading loads it alone.
        con.execute("INSTALL excel")
        con.execute("LOAD excel")
        con.execute(
            "CREATE TABLE sales AS SELECT * FROM (VALUES"
            " ('books', 10), ('toys', 5), ('books', 7)) t(category, amount)"
        )
        for ext, options in [
            ("csv", "FORMAT csv, HEADER true"),
            ("json", "FORMAT json, ARRAY true"),
            ("parquet", "FORMAT parquet"),
            ("xlsx", "FORMAT xlsx, HEADER true"),
        ]:
            con.execute(f"COPY sales TO '{folder / ('sales.' + ext)}' ({options})")
    return folder


@pytest.mark.parametrize(
    "name", ["sales.csv", "sales.json", "sales.parquet", "sales.xlsx"]
)
def test_every_table_format_is_grouped(table_files, tmp_path, name):
    path = resolve_upload(table_files, name)
    db = tmp_path / "a.duckdb"

    assert file_columns(path) == ["category", "amount"]
    assert save_groups(db, path, name, "category") == 2
    assert rows(db) == [(name, "category", "books", 2), (name, "category", "toys", 1)]


def test_other_files_are_refused(tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("hello")

    with pytest.raises(UploadError):
        file_columns(notes)


@pytest.mark.parametrize("path", ["../secret.csv", "/etc/passwd", "", "missing.csv"])
def test_path_must_point_to_a_file_inside_the_store(store, path):
    with pytest.raises(UploadError):
        resolve_upload(store, path)
