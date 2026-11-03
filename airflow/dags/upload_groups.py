"""Grouping an uploaded CSV by one column into DuckDB.

Plain functions with no Airflow import: the DAG calls them, and the app's
tests run them against a real DuckDB file without an Airflow install.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import duckdb

TABLE = "upload_groups"

CREATE_TABLE = f"""
    CREATE TABLE IF NOT EXISTS {TABLE} (
        source       VARCHAR NOT NULL,
        group_column VARCHAR NOT NULL,
        group_value  VARCHAR,
        row_count    BIGINT NOT NULL,
        processed_at TIMESTAMP NOT NULL DEFAULT current_timestamp
    )
"""


class UploadError(Exception):
    """The run cannot go on: no such file, or no such column in it."""


def resolve_upload(root: str | Path, relative: str) -> Path:
    """The uploaded file inside the shared folder.

    The path comes from the run's parameters, which anyone allowed to trigger
    the DAG can set, so it must not lead outside the folder.
    """
    parts = PurePosixPath(relative).parts
    if not parts or parts[0] == "/" or ".." in parts:
        raise UploadError(f"Bad path: {relative!r}")
    root = Path(root).resolve()
    target = root.joinpath(*parts).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise UploadError(f"No such file: {relative!r}")
    return target


def csv_columns(csv_path: Path) -> list[str]:
    with duckdb.connect() as con:
        return [
            row[0]
            for row in con.execute(
                "DESCRIBE SELECT * FROM read_csv_auto(?)", [str(csv_path)]
            ).fetchall()
        ]


def pick_column(columns: list[str], wanted: str | None) -> str:
    """The column to group by: the requested one, or the first."""
    if not columns:
        raise UploadError("The file has no columns.")
    if not wanted:
        return columns[0]
    if wanted not in columns:
        raise UploadError(f"No column {wanted!r}; the file has {columns}.")
    return wanted


def save_groups(db_path: str | Path, csv_path: Path, source: str, column: str) -> int:
    """Replace the groups of `source` with fresh ones; returns how many."""
    # A column name cannot be a query parameter, so it is quoted by hand.
    # It is one of the file's own columns already (pick_column).
    quoted = '"' + column.replace('"', '""') + '"'
    with duckdb.connect(str(db_path)) as con:
        con.execute(CREATE_TABLE)
        con.begin()
        # A file uploaded again under the same name must not count twice.
        con.execute(f"DELETE FROM {TABLE} WHERE source = ?", [source])
        con.execute(
            f"""
            INSERT INTO {TABLE} (source, group_column, group_value, row_count)
            SELECT ?, ?, CAST({quoted} AS VARCHAR), count(*)
            FROM read_csv_auto(?)
            GROUP BY {quoted}
            """,
            [source, column, str(csv_path)],
        )
        con.commit()
        return con.execute(
            f"SELECT count(*) FROM {TABLE} WHERE source = ?", [source]
        ).fetchone()[0]
