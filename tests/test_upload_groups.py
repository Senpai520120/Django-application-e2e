"""The DAG's grouping, run against a real DuckDB file."""

import duckdb
import pytest
from upload_groups import (
    UploadError,
    csv_columns,
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
    csv_path = resolve_upload(store, "reports/sales.csv")
    column = pick_column(csv_columns(csv_path), None)

    db = tmp_path / "a.duckdb"

    assert save_groups(db, csv_path, "reports/sales.csv", column) == 2
    assert rows(db) == [
        ("reports/sales.csv", "category", "books", 2),
        ("reports/sales.csv", "category", "toys", 1),
    ]


def test_same_file_again_replaces_its_groups(store, tmp_path):
    db = tmp_path / "a.duckdb"
    csv_path = resolve_upload(store, "reports/sales.csv")

    save_groups(db, csv_path, "reports/sales.csv", "category")
    save_groups(db, csv_path, "reports/sales.csv", "category")

    assert len(rows(db)) == 2


def test_requested_column_must_exist(store):
    columns = csv_columns(resolve_upload(store, "reports/sales.csv"))

    assert pick_column(columns, "amount") == "amount"
    with pytest.raises(UploadError):
        pick_column(columns, "price")


@pytest.mark.parametrize("path", ["../secret.csv", "/etc/passwd", "", "missing.csv"])
def test_path_must_point_to_a_file_inside_the_store(store, path):
    with pytest.raises(UploadError):
        resolve_upload(store, path)
