"""Finding new uploaded table files, grouping them by one column into DuckDB
and computing the asked-for math (sum, avg, ...) per group.

Plain functions with no Airflow import: the DAG calls them, and the app's
tests run them against a real DuckDB file without an Airflow install.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import duckdb

# DuckDB's reader for each table format. Keep in step with TABLE_FORMATS in
# files/pipeline.py, which decides what the app sends here. read_xlsx comes
# from the excel extension, installed into the Airflow image.
READERS = {
    ".csv": "read_csv_auto",
    ".json": "read_json_auto",
    ".parquet": "read_parquet",
    ".xlsx": "read_xlsx",
}

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

# Each file's result is a wide table of its own, result_<rule id>: one row
# per group, one column per math asked for. Files differ in their columns, so
# one shared table could not hold them all with real column types. The rule's
# id names the table, never the path: a path can hold any characters, and the
# id stays the same when the file is renamed.
RESULT_PREFIX = "result_"

# The long tables of the first version: one row per group in upload_groups,
# one row per group and op in upload_aggregates. Nothing writes them any
# more, and stale rows nobody updates would only mislead, so they are
# dropped the first time the DAG writes.
LEGACY_TABLES = ("upload_groups", "upload_aggregates")

# What is already done, so the sensor never takes a file twice. A row is one
# version of a file (its modification time) processed by one rule: its id
# (which names the result table), its column, its aggregations and its
# revision (how many times it was saved). The app reads it too, to tell
# whether result_<id> is the answer to the rule it has now.
PROCESSED = "processed_files"

CREATE_PROCESSED = f"""
    CREATE TABLE IF NOT EXISTS {PROCESSED} (
        source       VARCHAR PRIMARY KEY,
        mtime_ms     BIGINT NOT NULL,
        group_by     VARCHAR NOT NULL,
        aggregations VARCHAR NOT NULL DEFAULT '[]',
        revision     BIGINT NOT NULL DEFAULT 0,
        rule_id      BIGINT,
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

# And for the rule id. Rows from before it are NULL, which never equals a
# rule's id, so every old file is processed once more into a table of its own.
ADD_RULE_ID_COLUMN = f"""
    ALTER TABLE {PROCESSED}
    ADD COLUMN IF NOT EXISTS rule_id BIGINT
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


# How long opening the database waits for a reader to let go. DuckDB lets
# either one writing process or any number of reading ones hold the file, and
# the app opens it read-only for a moment on every Results page.
LOCK_WAIT_SECONDS = 10.0


def connect(database: str | Path = ":memory:") -> duckdb.DuckDBPyConnection:
    """A DuckDB connection that can also read the app's s3:// files."""
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        try:
            con = duckdb.connect(str(database))
            break
        except duckdb.IOException as error:
            # Only a lock is worth waiting for; a broken file is not.
            if "lock" not in str(error).lower() or time.monotonic() >= deadline:
                raise
            time.sleep(0.2)
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

    Each rule also has "id" (it names the result table), "configured" (False:
    a draft) and "revision" (how many times the user saved it).

    Any failure raises: the sensor must not guess the columns while the app
    is down, it fails and is retried instead.
    """
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return {
            rule["path"]: {
                # None from an app that sends no ids: pending() then waits.
                "id": rule.get("id"),
                "group_by": rule["group_by"],
                "aggregations": rule.get("aggregations", []),
                # An app without drafts sends no flag: all its rules are final.
                "configured": rule.get("configured", True),
                "revision": rule.get("revision", 0),
            }
            for rule in json.load(response)
        }


def aggregations_key(aggregations: Sequence[Mapping[str, str]]) -> str:
    """The aggregations as stable text, to compare with what was done.

    Never raises on a broken rule (no "column", not even a dict): the sensor
    runs this for every file, and one bad rule must not stop all of them.
    check_aggregations refuses it later, and only that file is marked failed.
    """
    if not isinstance(aggregations, (list, tuple)):
        return json.dumps(repr(aggregations))
    items = [
        (
            {"op": item.get("op"), "column": item.get("column")}
            if isinstance(item, Mapping)
            else repr(item)
        )
        for item in aggregations
    ]
    return json.dumps(items, sort_keys=True, separators=(",", ":"))


def _ensure_processed(con) -> None:
    con.execute(CREATE_PROCESSED)
    con.execute(ADD_AGGREGATIONS_COLUMN)
    con.execute(ADD_REVISION_COLUMN)
    con.execute(ADD_RULE_ID_COLUMN)


def processed_files(
    db_path: str | Path,
) -> dict[str, tuple[int, str, str, int, int | None]]:
    """{source: (modified time in ms, column, aggregations_key, revision, rule id)}."""
    with connect(db_path) as con:
        _ensure_processed(con)
        rows = con.execute(
            f"SELECT source, mtime_ms, group_by, aggregations, revision, rule_id"
            f" FROM {PROCESSED}"
        )
        return {source: tuple(rest) for source, *rest in rows.fetchall()}


def pending(
    files: Mapping[str, int],
    rules: Mapping[str, Mapping],
    processed: Mapping[str, tuple[int, str, str, int, int | None]],
) -> list[dict]:
    """The files to process now: new, changed, or with a newly saved rule.

    A file waits while the user has not chosen its column: its rule is a
    draft, or it has no rule at all (renamed from .txt to .csv, uploaded while
    grouping was off). With no rule there is no id to name its result table
    either; saving the grouping page makes one. A file that failed is done
    too: it is not tried again until it is uploaded anew or its rule is saved
    again, even unchanged, which bumps the revision.
    """
    todo = []
    for path, mtime_ms in sorted(files.items()):
        rule = rules.get(path)
        if rule is None or not rule.get("configured", True):
            continue
        rule_id = rule.get("id")
        if not isinstance(rule_id, int):
            # No id, no table name: an app too old to send one.
            continue
        group_by = rule.get("group_by") or ""
        aggregations = rule.get("aggregations") or []
        # Not a list (a rule broken by hand) is handed on as it is:
        # check_aggregations fails this one file instead of the sensor.
        revision = rule.get("revision", 0)
        done = (
            mtime_ms,
            group_by,
            aggregations_key(aggregations),
            revision,
            rule_id,
        )
        if processed.get(path) != done:
            todo.append(
                {
                    "path": path,
                    "rule_id": rule_id,
                    "mtime_ms": mtime_ms,
                    "group_by": group_by,
                    "aggregations": aggregations,
                    "revision": revision,
                }
            )
    return todo


def forget_removed(
    db_path: str | Path,
    files: Mapping[str, int],
    rules: Mapping[str, Mapping],
    processed: Mapping[str, tuple],
) -> list[str]:
    """Drop the results no saved rule stands behind; returns their paths.

    A result lives only while its file has a configured rule: the rules come
    from the app's API, which fails loudly instead of answering empty. So a
    deleted or renamed file (its rule deleted or moved), a file uploaded
    again under the same name (a draft again) and a file with no rule (the
    list shows it as waiting) all lose their rows, and one Save brings them
    back from the file. The listing only adds files removed behind the app's
    back (an S3 console), and only when it is not empty: an empty one may be
    an unmounted volume or S3 not answering, never a reason to delete.

    Their result_<id> tables go too: a table lives only while a done row of
    processed_files points at it. A renamed file keeps its rule and so its
    id, but its new path has no row yet; the next tick makes the table again
    from the file under its new name.
    """
    configured = {path for path, rule in rules.items() if rule.get("configured", True)}
    gone = {path for path in processed if path not in configured}
    if files:
        gone |= set(processed) - set(files)
    gone = sorted(gone)
    if not gone:
        # The usual tick: no write, so no write lock on DuckDB.
        return []
    with connect(db_path) as con:
        _ensure_processed(con)
        con.begin()
        con.execute(f"DELETE FROM {PROCESSED} WHERE list_contains(?, source)", [gone])
        _drop_unused_results(con)
        con.commit()
    return gone


def result_table(rule_id: int) -> str:
    """The name of a file's result table; int() keeps it a plain name."""
    return f"{RESULT_PREFIX}{int(rule_id)}"


_RESULT_NAME = re.compile(rf"{RESULT_PREFIX}([0-9]+)")


def result_tables(con) -> dict[int, str]:
    """{rule id: table name} of every result table in the database."""
    names = con.execute(
        "SELECT table_name FROM duckdb_tables() WHERE schema_name = 'main'"
    ).fetchall()
    return {
        int(match[1]): name
        for (name,) in names
        if (match := _RESULT_NAME.fullmatch(name))
    }


def _drop_unused_results(con) -> None:
    """Drop the result tables no done row points at, and the old long tables.

    Runs inside the caller's transaction, so a result table and its row of
    processed_files appear and go away together.
    """
    used = {
        row[0]
        for row in con.execute(
            f"SELECT rule_id FROM {PROCESSED}"
            " WHERE status = 'done' AND rule_id IS NOT NULL"
        ).fetchall()
    }
    for rule_id, name in result_tables(con).items():
        if rule_id not in used:
            con.execute(f"DROP TABLE {_quote(name)}")
    for name in LEGACY_TABLES:
        con.execute(f"DROP TABLE IF EXISTS {name}")


def _mark(
    con,
    source: str,
    rule_id: int | None,
    mtime_ms: int,
    group_by: str,
    aggregations: Sequence[Mapping[str, str]],
    revision: int,
    error: str | None,
) -> None:
    con.execute(
        f"""
        INSERT OR REPLACE INTO {PROCESSED}
            (source, rule_id, mtime_ms, group_by, aggregations, revision, status,
             error, processed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
        """,
        [
            source,
            rule_id,
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
    rule_id: int | None = None,
) -> None:
    """Remember a file that cannot be processed, so it is not tried every tick.

    Its old result table goes too: the app shows the error instead, and a
    table from an earlier rule must not pass for the answer to this one.
    """
    with connect(db_path) as con:
        _ensure_processed(con)
        con.begin()
        _mark(con, source, rule_id, mtime_ms, group_by, aggregations, revision, error)
        _drop_unused_results(con)
        con.commit()


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
    if not isinstance(aggregations, (list, tuple)):
        raise UploadError(f"Bad aggregations {aggregations!r}; expected a list.")
    types = dict(schema)
    checked = []
    for item in aggregations:
        if not isinstance(item, Mapping):
            raise UploadError(f"Bad aggregation {item!r}; expected op and column.")
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


ROW_COUNT = "row_count"


def result_columns(column: str, aggregations: Sequence[Mapping[str, str]]) -> list[str]:
    """Column names of a result table: the group column, row_count, op_column...

    A name already taken gets _2, _3, ... in the order the columns come: a
    file may well have a column of its own called row_count, or one called
    sum_amount next to amount. DuckDB compares names without case, so
    "Sum_amount" is taken by "sum_amount" too.
    """
    taken: set[str] = set()
    names = []
    for wanted in [column, ROW_COUNT] + [
        f"{item['op']}_{item['column']}" for item in aggregations
    ]:
        name, number = wanted, 1
        while name.lower() in taken:
            number += 1
            name = f"{wanted}_{number}"
        taken.add(name.lower())
        names.append(name)
    return names


def save_groups(
    db_path: str | Path,
    path: str | Path,
    source: str,
    column: str,
    *,
    rule_id: int,
    mtime_ms: int,
    group_by: str,
    aggregations: Sequence[Mapping[str, str]] = (),
    revision: int = 0,
) -> int:
    """Write the result table of `source` anew; returns how many groups.

    The table is result_<rule_id>: the group column, row_count and one column
    per aggregation (sum_amount, ...), with the types DuckDB gives them. CREATE
    OR REPLACE makes it from scratch every time, so a rule with other math
    gets a table of another shape. `aggregations` must come from
    check_aggregations. The same transaction marks the file done with its
    modified time and its rule (`group_by`, maybe empty, the aggregations and
    the revision), so the table and the mark never disagree.
    """
    table = result_table(rule_id)
    names = [_quote(name) for name in result_columns(column, aggregations)]
    # The group column and the aggregated ones are the file's own already
    # (pick_group_column, check_aggregations), the functions come from
    # AGGREGATES, and every name is quoted.
    selected = [f"{_quote(column)} AS {names[0]}", f"count(*) AS {names[1]}"]
    for item, name in zip(aggregations, names[2:], strict=True):
        function = AGGREGATES[item["op"]]
        selected.append(f"{function}({_quote(item['column'])}) AS {name}")
    with connect(db_path) as con:
        _ensure_processed(con)
        con.begin()
        # The file is read once into memory; uploads are small
        # (FILE_MANAGER_MAX_FILE_SIZE).
        con.execute(
            f"CREATE TEMP TABLE upload AS SELECT * FROM {reader(path)}(?)",
            [str(path)],
        )
        # Ordered by the group, so the table reads well as it is.
        con.execute(f"""
            CREATE OR REPLACE TABLE {table} AS
            SELECT {", ".join(selected)}
            FROM upload
            GROUP BY 1
            ORDER BY 1 NULLS LAST
            """)
        _mark(con, source, rule_id, mtime_ms, group_by, aggregations, revision, None)
        # The file's table under an older rule (uploaded again under the same
        # name), and the old long tables, go in the same step.
        _drop_unused_results(con)
        con.commit()
        row = con.execute(f"SELECT count(*) FROM {table}").fetchone()
        # count(*) always gives one row; fetchone() is typed as maybe None.
        assert row is not None
        return row[0]
