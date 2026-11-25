"""Finding new uploaded table files, grouping them by one column into DuckDB
and computing the asked-for math (sum, avg, ...) per group.

Plain functions with no Airflow import: the DAG calls them, and the app's
tests run them against a real DuckDB file without an Airflow install.
"""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Mapping, Sequence
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


# Math per group asked for in the app: op -> DuckDB function. Keep in step
# with AGGREGATIONS in files/pipeline.py. Only these names ever reach SQL.
AGGREGATES = {"sum": "sum", "avg": "avg", "min": "min", "max": "max", "count": "count"}

# The ops that need numbers; count takes any column.
NUMERIC_ONLY = {"sum", "avg", "min", "max"}

NUMERIC_TYPES = {
    "TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT",
    "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT", "UHUGEINT",
    "FLOAT", "DOUBLE",
}  # fmt: skip

# One row per group and op: the set of ops differs from file to file, and a
# long table keeps one schema for all of them.
AGGREGATES_TABLE = "upload_aggregates"

CREATE_AGGREGATES = f"""
    CREATE TABLE IF NOT EXISTS {AGGREGATES_TABLE} (
        source       VARCHAR NOT NULL,
        group_column VARCHAR NOT NULL,
        group_value  VARCHAR,
        op           VARCHAR NOT NULL,
        value_column VARCHAR NOT NULL,
        value        DOUBLE,
        processed_at TIMESTAMP NOT NULL DEFAULT current_timestamp
    )
"""

# What is already done, so the sensor never takes a file twice. A row is one
# version of a file (its modification time) processed by one rule: its
# column, its aggregations and its revision (how many times it was saved).
PROCESSED = "processed_files"

CREATE_PROCESSED = f"""
    CREATE TABLE IF NOT EXISTS {PROCESSED} (
        source       VARCHAR PRIMARY KEY,
        mtime_ms     BIGINT NOT NULL,
        group_by     VARCHAR NOT NULL,
        aggregations VARCHAR NOT NULL DEFAULT '[]',
        revision     BIGINT NOT NULL DEFAULT 0,
        status       VARCHAR NOT NULL,
        error        VARCHAR,
        processed_at TIMESTAMP NOT NULL DEFAULT current_timestamp
    )
"""

# A database made before aggregations existed lacks the column; '[]' is
# what those files were processed with, so they are not taken again. No NOT
# NULL here: DuckDB cannot add one with IF NOT EXISTS, and the default fills
# the old rows anyway.
ADD_AGGREGATIONS_COLUMN = f"""
    ALTER TABLE {PROCESSED}
    ADD COLUMN IF NOT EXISTS aggregations VARCHAR DEFAULT '[]'
"""

# The same for the revision: 0 is what an app without revisions sends.
ADD_REVISION_COLUMN = f"""
    ALTER TABLE {PROCESSED}
    ADD COLUMN IF NOT EXISTS revision BIGINT DEFAULT 0
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


def list_table_files(root: str | Path) -> dict[str, int]:
    """Every table file under `root`: {path inside it: modified time in ms}.

    read_blob lists the files of a folder or of a bucket prefix alike and
    reads no content unless asked for it. An empty or missing folder gives {}.
    """
    base = str(root).rstrip("/\\")
    with connect() as con:
        found = con.execute(
            "SELECT filename, epoch_ms(last_modified) FROM read_blob(?)",
            [f"{base}/**"],
        ).fetchall()
    files = {}
    for filename, mtime_ms in found:
        # Windows separators in tests; the containers have only "/".
        relative = filename[len(base) :].replace("\\", "/").lstrip("/")
        if PurePosixPath(relative).suffix.lower() in READERS:
            files[relative] = mtime_ms
    return files


def fetch_rules(url: str, token: str, timeout: float = 5) -> dict[str, dict]:
    """The rules from the app's API: {path: {"group_by", "aggregations", ...}}.

    Each rule also has "configured" (False: a draft) and "revision" (how many
    times the user saved it).

    Any failure raises: the sensor must not guess the columns while the app
    is down, it fails and is retried instead.
    """
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return {
            rule["path"]: {
                "group_by": rule["group_by"],
                "aggregations": rule.get("aggregations", []),
                # An app without drafts sends no flag: all its rules are final.
                "configured": rule.get("configured", True),
                "revision": rule.get("revision", 0),
            }
            for rule in json.load(response)
        }


def aggregations_key(aggregations: Sequence[Mapping[str, str]]) -> str:
    """The aggregations as stable text, to compare with what was done."""
    items = [{"op": item["op"], "column": item["column"]} for item in aggregations]
    return json.dumps(items, sort_keys=True, separators=(",", ":"))


def _ensure_processed(con) -> None:
    con.execute(CREATE_PROCESSED)
    con.execute(ADD_AGGREGATIONS_COLUMN)
    con.execute(ADD_REVISION_COLUMN)


def processed_files(db_path: str | Path) -> dict[str, tuple[int, str, str, int]]:
    """{source: (modified time in ms, column, aggregations_key, revision)}."""
    with connect(db_path) as con:
        _ensure_processed(con)
        rows = con.execute(
            f"SELECT source, mtime_ms, group_by, aggregations, revision"
            f" FROM {PROCESSED}"
        )
        return {source: tuple(rest) for source, *rest in rows.fetchall()}


def pending(
    files: Mapping[str, int],
    rules: Mapping[str, Mapping],
    processed: Mapping[str, tuple[int, str, str, int]],
) -> list[dict]:
    """The files to process now: new, changed, or with a newly saved rule.

    A file waits while the user has not chosen its column: its rule is a
    draft, or it has no rule at all (renamed from .txt to .csv, uploaded while
    grouping was off). A file that failed is done too: it is not tried again
    until it is uploaded anew or its rule is saved again, even unchanged, which
    bumps the revision.
    """
    todo = []
    for path, mtime_ms in sorted(files.items()):
        rule = rules.get(path)
        if rule is None or not rule.get("configured", True):
            continue
        group_by = rule.get("group_by", "")
        aggregations = list(rule.get("aggregations", []))
        revision = rule.get("revision", 0)
        done = (mtime_ms, group_by, aggregations_key(aggregations), revision)
        if processed.get(path) != done:
            todo.append(
                {
                    "path": path,
                    "mtime_ms": mtime_ms,
                    "group_by": group_by,
                    "aggregations": aggregations,
                    "revision": revision,
                }
            )
    return todo


def _mark(
    con,
    source: str,
    mtime_ms: int,
    group_by: str,
    aggregations: Sequence[Mapping[str, str]],
    revision: int,
    error: str | None,
) -> None:
    _ensure_processed(con)
    con.execute(
        f"""
        INSERT OR REPLACE INTO {PROCESSED}
            (source, mtime_ms, group_by, aggregations, revision, status, error,
             processed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, current_timestamp)
        """,
        [
            source,
            mtime_ms,
            group_by,
            aggregations_key(aggregations),
            revision,
            "failed" if error else "done",
            error,
        ],
    )


def mark_failed(
    db_path: str | Path,
    source: str,
    mtime_ms: int,
    group_by: str,
    aggregations: Sequence[Mapping[str, str]],
    error: str,
    revision: int = 0,
) -> None:
    """Remember a file that cannot be processed, so it is not tried every tick."""
    with connect(db_path) as con:
        _mark(con, source, mtime_ms, group_by, aggregations, revision, error)


def reader(path: str | Path) -> str:
    """The DuckDB function that reads the file, chosen by its extension."""
    # PurePosixPath, not Path: Path would fold the // of s3://.
    name = PurePosixPath(str(path))
    try:
        return READERS[name.suffix.lower()]
    except KeyError:
        raise UploadError(f"Not a table file: {name.name!r}") from None


def file_schema(path: str | Path) -> list[tuple[str, str]]:
    """(name, DuckDB type) of each column, as DuckDB reads the file."""
    with connect() as con:
        return [
            (row[0], row[1])
            for row in con.execute(
                f"DESCRIBE SELECT * FROM {reader(path)}(?)", [str(path)]
            ).fetchall()
        ]


def file_columns(path: str | Path) -> list[str]:
    return [name for name, _ in file_schema(path)]


def pick_column(columns: list[str], wanted: str | None) -> str:
    """The column to group by: the requested one, or the first."""
    if not columns:
        raise UploadError("The file has no columns.")
    if not wanted:
        return columns[0]
    if wanted not in columns:
        raise UploadError(f"No column {wanted!r}; the file has {columns}.")
    return wanted


def pick_group_column(schema: list[tuple[str, str]], wanted: str | None) -> str:
    """The column to group by: the requested one, else the first text column.

    A text (VARCHAR) column is the natural thing to group by; an id or an
    amount is not. With no text column at all, the first column is used.
    """
    names = [name for name, _ in schema]
    if wanted:
        return pick_column(names, wanted)
    for name, type_ in schema:
        if type_.upper() == "VARCHAR":
            return name
    return pick_column(names, None)


def check_aggregations(
    schema: list[tuple[str, str]], aggregations: Sequence[Mapping[str, str]]
) -> list[dict]:
    """The aggregations, checked against the file: known op, real column, numbers.

    The app checks the ops too, but the columns only the file can tell.
    """
    types = dict(schema)
    checked = []
    for item in aggregations:
        op, column = item.get("op"), item.get("column")
        if op not in AGGREGATES:
            raise UploadError(
                f"Unknown aggregation {op!r}; use one of {list(AGGREGATES)}."
            )
        if column not in types:
            raise UploadError(f"No column {column!r}; the file has {list(types)}.")
        type_ = types[column].upper()
        numeric = type_ in NUMERIC_TYPES or type_.startswith("DECIMAL")
        if op in NUMERIC_ONLY and not numeric:
            raise UploadError(f"{op}({column}): {column!r} is {type_}, not a number.")
        checked.append({"op": op, "column": column})
    return checked


def _quote(name: str) -> str:
    """A column name for SQL: names cannot be query parameters."""
    return '"' + name.replace('"', '""') + '"'


def save_groups(
    db_path: str | Path,
    path: str | Path,
    source: str,
    column: str,
    *,
    mtime_ms: int,
    group_by: str,
    aggregations: Sequence[Mapping[str, str]] = (),
    revision: int = 0,
) -> int:
    """Replace the groups and aggregates of `source`; returns how many groups.

    `aggregations` must come from check_aggregations. The same transaction
    marks the file done with its modified time and its rule (`group_by`,
    maybe empty, the aggregations and the revision), so the results and the mark never
    disagree.
    """
    # Both are the file's own columns already (pick_column, check_aggregations).
    group = _quote(column)
    with connect(db_path) as con:
        con.execute(CREATE_TABLE)
        con.execute(CREATE_AGGREGATES)
        con.begin()
        # The file is read once into memory for all the queries below; uploads
        # are small (FILE_MANAGER_MAX_FILE_SIZE).
        con.execute(
            f"CREATE TEMP TABLE upload AS SELECT * FROM {reader(path)}(?)",
            [str(path)],
        )
        # A file uploaded again under the same name must not count twice.
        con.execute(f"DELETE FROM {TABLE} WHERE source = ?", [source])
        con.execute(f"DELETE FROM {AGGREGATES_TABLE} WHERE source = ?", [source])
        con.execute(
            f"""
            INSERT INTO {TABLE} (source, group_column, group_value, row_count)
            SELECT ?, ?, CAST({group} AS VARCHAR), count(*)
            FROM upload
            GROUP BY {group}
            """,
            [source, column],
        )
        for item in aggregations:
            function = AGGREGATES[item["op"]]
            con.execute(
                f"""
                INSERT INTO {AGGREGATES_TABLE}
                    (source, group_column, group_value, op, value_column, value)
                SELECT ?, ?, CAST({group} AS VARCHAR), ?, ?,
                       CAST({function}({_quote(item["column"])}) AS DOUBLE)
                FROM upload
                GROUP BY {group}
                """,
                [source, column, item["op"], item["column"]],
            )
        _mark(con, source, mtime_ms, group_by, aggregations, revision, None)
        con.commit()
        row = con.execute(
            f"SELECT count(*) FROM {TABLE} WHERE source = ?", [source]
        ).fetchone()
        # count(*) always gives one row; fetchone() is typed as maybe None.
        assert row is not None
        return row[0]
