"""The grouping result of a table file, read from Airflow's DuckDB file.

Airflow writes each file's result into a table of its own, result_<rule id>,
and remembers what it did in processed_files (airflow/dags/upload_groups.py).
The app only reads: it opens the file read-only, and docker-compose.airflow.yml
mounts the analytics volume into the app read-only too.

DuckDB lets either one writing process or any number of reading ones hold the
file. While Airflow writes, the app cannot open it and says so; Airflow, for
its part, waits a few seconds for a reader to let go.
"""

import datetime
import logging
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
from django.conf import settings

from files.pipeline import processing_enabled

log = logging.getLogger(__name__)

# A page with more groups than this is cut, and says so: the page is for a
# look at the result, not for a download of it.
MAX_ROWS = 500

# The states of the page, also its data-state attribute for the E2E tests.
WAITING = "waiting"  # Airflow has not processed the file's current rule yet
BUSY = "busy"  # Airflow is writing right now
FAILED = "failed"
DONE = "done"


@dataclass
class Result:
    state: str
    error: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    # Groups in the whole table; more than len(rows) when the page is cut.
    total: int = 0

    @property
    def truncated(self) -> bool:
        return self.total > len(self.rows)


def results_enabled() -> bool:
    """On with the grouping and a DuckDB file to read, as in the Airflow stack."""
    return processing_enabled() and bool(settings.DUCKDB_PATH)


def result_table(rule_id: int) -> str:
    """Keep in step with result_table in airflow/dags/upload_groups.py."""
    return f"result_{int(rule_id)}"


def read_result(rule) -> Result:
    """What Airflow made of the file of a configured `rule` (a GroupingRule)."""
    database = Path(settings.DUCKDB_PATH)
    if not database.is_file():
        # Airflow has not written anything yet, or has not started at all.
        return Result(WAITING)
    try:
        with duckdb.connect(str(database), read_only=True) as con:
            return _read(con, rule)
    except duckdb.IOException as error:
        if "lock" not in str(error).lower():
            raise
        log.info("DuckDB is busy, the results page asks to refresh: %s", error)
        return Result(BUSY)


def _read(con, rule) -> Result:
    try:
        row = con.execute(
            "SELECT rule_id, revision, status, error FROM processed_files"
            " WHERE source = ?",
            [rule.path],
        ).fetchone()
    except (duckdb.CatalogException, duckdb.BinderException):
        # No processed_files yet, or one from before rule ids: nothing of
        # this rule has been written.
        return Result(WAITING)
    # Only an answer to the rule as it is now counts: the same id (the file
    # was not deleted and uploaded again) and the same revision (the grouping
    # was not saved again since). The file's own time is not compared: the
    # app never overwrites a file, a new upload under the same name gets a
    # new rule and so a new id.
    if row is None or row[0] != rule.pk or row[1] != rule.revision:
        return Result(WAITING)
    _rule_id, _revision, status, error = row
    if status != "done":
        return Result(FAILED, error=error or "")
    table = result_table(rule.pk)
    try:
        cursor = con.execute(
            f"SELECT * FROM {table} ORDER BY 1 NULLS LAST LIMIT {MAX_ROWS}"
        )
    except duckdb.CatalogException:
        # The DAG writes the table and its row in one transaction, so only a
        # database changed by hand gets here; that must not take the page down.
        return Result(WAITING)
    columns = [column[0] for column in cursor.description]
    rows = [tuple(_as_stored(value) for value in row) for row in cursor.fetchall()]
    total = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    return Result(DONE, columns=columns, rows=rows, total=total)


def _as_stored(value):
    """A date or time as SQL over the table shows it (2026-11-01), not as
    Django would format it for the locale (Nov. 1, 2026)."""
    if isinstance(value, datetime.datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, (datetime.date, datetime.time)):
        return value.isoformat()
    return value
