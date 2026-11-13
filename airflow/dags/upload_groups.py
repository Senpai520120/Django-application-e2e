"""Grouping an uploaded table file by one column into DuckDB.

Plain functions with no Airflow import: the DAG calls them, and the app's
tests run them against a real DuckDB file without an Airflow install.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import duckdb

TABLE = "upload_groups"

# DuckDB's reader for each table format. Keep in step with TABLE_FORMATS in
# files/pipeline.py, which decides what the app sends here. read_xlsx comes
# from the excel extension, installed into the Airflow image.
READERS = {
    ".csv": "read_csv_auto",
    ".json": "read_json_auto",
    ".parquet": "read_parquet",
    ".xlsx": "read_xlsx",
}

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
    """The run cannot go on: no such file, an unknown format, or no such column."""


def filestore_root(env: Mapping[str, str]) -> str:
    """Where the app keeps uploads, read from the app's own storage settings.

    Local storage is the shared volume; s3 is the bucket and the key prefix
    the file manager writes under (FILE_MANAGER_S3_LOCATION).
    """
    if env.get("FILE_STORAGE_BACKEND") != "s3":
        return env.get("FILESTORE_ROOT", "/data/filestore")
    bucket = env.get("AWS_STORAGE_BUCKET_NAME")
    if not bucket:
        raise UploadError("FILE_STORAGE_BACKEND=s3 needs AWS_STORAGE_BUCKET_NAME.")
    location = env.get("FILE_MANAGER_S3_LOCATION", "filemanager").strip("/")
    return f"s3://{bucket}/{location}" if location else f"s3://{bucket}"


def s3_secret(env: Mapping[str, str]) -> str | None:
    """CREATE SECRET that lets DuckDB read the app's bucket; None off s3.

    Uses the names django-storages reads, so the bucket settings match the
    app's. The keys are Airflow's own read-only pair, which
    docker-compose.airflow.yml maps from AIRFLOW_AWS_*.
    """
    if env.get("FILE_STORAGE_BACKEND") != "s3":
        return None
    options = [
        "TYPE s3",
        f"REGION {_text(env.get('AWS_S3_REGION_NAME') or 'eu-central-1')}",
    ]
    key_id = env.get("AWS_ACCESS_KEY_ID")
    secret = env.get("AWS_SECRET_ACCESS_KEY")
    if key_id and secret:
        options += [f"KEY_ID {_text(key_id)}", f"SECRET {_text(secret)}"]
    else:
        # No keys: the instance role or ~/.aws, as boto3 would find them.
        options.append("PROVIDER credential_chain")
    endpoint = env.get("AWS_S3_ENDPOINT_URL")
    if endpoint:
        # DuckDB wants host:port and the scheme as a separate switch.
        url = urlsplit(endpoint)
        options += [
            f"ENDPOINT {_text(url.netloc)}",
            f"USE_SSL {'true' if url.scheme == 'https' else 'false'}",
        ]
    if env.get("AWS_S3_ADDRESSING_STYLE") == "path":
        options.append("URL_STYLE 'path'")
    return f"CREATE SECRET ({', '.join(options)})"


def _text(value: str) -> str:
    """A string literal for SQL that takes no parameters, like CREATE SECRET."""
    return "'" + value.replace("'", "''") + "'"


def connect(database: str | Path = ":memory:") -> duckdb.DuckDBPyConnection:
    """A DuckDB connection that can also read the app's s3:// files."""
    con = duckdb.connect(str(database))
    secret = s3_secret(os.environ)
    if secret:
        con.execute(secret)
    return con


def resolve_upload(root: str | Path, relative: str) -> str:
    """The uploaded file inside the shared folder or the bucket.

    The path comes from the run's parameters, which anyone allowed to trigger
    the DAG can set, so it must not lead outside the folder.
    """
    parts = PurePosixPath(relative).parts
    if not parts or parts[0] == "/" or ".." in parts:
        raise UploadError(f"Bad path: {relative!r}")
    if str(root).startswith("s3://"):
        # A key is plain text with nothing to resolve, and a missing object
        # fails the first read of it.
        return "/".join([str(root).rstrip("/"), *parts])
    root = Path(root).resolve()
    target = root.joinpath(*parts).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise UploadError(f"No such file: {relative!r}")
    return str(target)


def reader(path: str | Path) -> str:
    """The DuckDB function that reads the file, chosen by its extension."""
    # PurePosixPath, not Path: Path would fold the // of s3://.
    name = PurePosixPath(str(path))
    try:
        return READERS[name.suffix.lower()]
    except KeyError:
        raise UploadError(f"Not a table file: {name.name!r}") from None


def file_columns(path: str | Path) -> list[str]:
    with connect() as con:
        return [
            row[0]
            for row in con.execute(
                f"DESCRIBE SELECT * FROM {reader(path)}(?)", [str(path)]
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


def save_groups(db_path: str | Path, path: str | Path, source: str, column: str) -> int:
    """Replace the groups of `source` with fresh ones; returns how many."""
    # A column name cannot be a query parameter, so it is quoted by hand.
    # It is one of the file's own columns already (pick_column).
    quoted = '"' + column.replace('"', '""') + '"'
    with connect(db_path) as con:
        con.execute(CREATE_TABLE)
        con.begin()
        # A file uploaded again under the same name must not count twice.
        con.execute(f"DELETE FROM {TABLE} WHERE source = ?", [source])
        con.execute(
            f"""
            INSERT INTO {TABLE} (source, group_column, group_value, row_count)
            SELECT ?, ?, CAST({quoted} AS VARCHAR), count(*)
            FROM {reader(path)}(?)
            GROUP BY {quoted}
            """,
            [source, column, str(path)],
        )
        con.commit()
        row = con.execute(
            f"SELECT count(*) FROM {TABLE} WHERE source = ?", [source]
        ).fetchone()
        # count(*) always gives one row; fetchone() is typed as maybe None.
        assert row is not None
        return row[0]
