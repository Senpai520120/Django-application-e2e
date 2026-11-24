"""Uploaded table files and the grouping in Airflow.

The app never calls Airflow. It stores a GroupingRule next to each table file,
and the watch_uploads DAG (airflow/dags/watch_uploads.py) finds new files by
itself and reads their rules from the grouping-rules API. The app reads only
a file's column names and types (file_schema), so the grouping page can offer
the real columns to choose from.
"""

import shutil
import tempfile
from pathlib import PurePosixPath

import duckdb
from django.conf import settings

# Formats the DAG can read, with DuckDB's reader for each; keep in step with
# READERS in airflow/dags/upload_groups.py. Other files are only stored.
# read_xlsx comes from the excel extension, installed into both images.
TABLE_READERS = {
    ".csv": "read_csv_auto",
    ".xlsx": "read_xlsx",
    ".json": "read_json_auto",
    ".parquet": "read_parquet",
}
TABLE_FORMATS = tuple(TABLE_READERS)

# Math that can be asked for per group; keep in step with AGGREGATES in
# airflow/dags/upload_groups.py. count works on any column, the rest on
# numbers only.
AGGREGATIONS = ("sum", "avg", "min", "max", "count")
NUMERIC_ONLY = ("sum", "avg", "min", "max")

# What each op answers, shown on the grouping page next to its checkbox.
AGGREGATION_HINTS = {
    "sum": "how much in total",
    "avg": "average value",
    "min": "smallest value",
    "max": "largest value",
    "count": "how many are filled in",
}

# More would make the results table hard to read and the query slow.
MAX_AGGREGATIONS = 10

# DuckDB's number types (DECIMAL(p, s) is matched by its prefix); keep in step
# with NUMERIC_TYPES in airflow/dags/upload_groups.py, which checks again.
NUMERIC_TYPES = {
    "TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT",
    "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT", "UHUGEINT",
    "FLOAT", "DOUBLE",
}  # fmt: skip


class SchemaError(Exception):
    """The file cannot be read as a table."""


def processing_enabled() -> bool:
    """On when Airflow has a token to read the rules with."""
    return bool(settings.PIPELINE_API_TOKEN)


def is_table(name: str) -> bool:
    return PurePosixPath(name).suffix.lower() in TABLE_READERS


def should_process(name: str) -> bool:
    return processing_enabled() and is_table(name)


def is_numeric(duckdb_type: str) -> bool:
    type_ = duckdb_type.upper()
    return type_ in NUMERIC_TYPES or type_.startswith("DECIMAL")


def file_schema(storage, path: str) -> list[tuple[str, str]]:
    """(name, DuckDB type) of each column of the file at `path`, as Airflow sees it.

    The file is copied to a temporary file first: that works the same for the
    local disk and for S3, and uploads are small (FILE_MANAGER_MAX_FILE_SIZE).
    DuckDB is the same reader Airflow uses, so the columns and types offered
    here are the ones the DAG will find.
    """
    suffix = PurePosixPath(path).suffix.lower()
    reader = TABLE_READERS.get(suffix)
    if reader is None:
        raise SchemaError("Not a table file.")
    # Closed before DuckDB opens it (Windows will not share an open temporary
    # file), removed when the block ends.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete_on_close=False) as copy:
        with storage.open(path) as source:
            shutil.copyfileobj(source, copy)
        copy.close()
        try:
            with duckdb.connect() as con:
                rows = con.execute(
                    f"DESCRIBE SELECT * FROM {reader}(?)", [copy.name]
                ).fetchall()
        except duckdb.Error as error:
            raise SchemaError(str(error).splitlines()[0]) from error
    return [(row[0], row[1]) for row in rows]


def describe_aggregations(aggregations: list[dict]) -> str:
    """Short form for messages: "sum(clicks), avg(impressions)"."""
    return ", ".join(f"{item['op']}({item['column']})" for item in aggregations)
