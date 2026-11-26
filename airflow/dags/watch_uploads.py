"""Watch the file manager's uploads and group every new table file into DuckDB.

Nobody triggers it: the run never stops for long. A sensor looks at the
uploads every 30 seconds, asks the app which column each file is grouped by,
and hands the new or changed files on, one task per file. Each file's result
is a table of its own, result_<rule id>, which the app's Results page shows.
When they are done the run ends and @continuous starts the next one at once.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta

import duckdb
from airflow.sdk import PokeReturnValue, dag, task
from upload_groups import (
    UploadError,
    check_aggregations,
    fetch_rules,
    file_schema,
    filestore_root,
    forget_removed,
    list_table_files,
    mark_failed,
    pending,
    pick_group_column,
    processed_files,
    resolve_upload,
    save_groups,
)

log = logging.getLogger(__name__)

DUCKDB_PATH = os.environ.get("DUCKDB_PATH", "/data/analytics/analytics.duckdb")


@dag(
    schedule="@continuous",
    # Required in practice: without it the first run gets an empty interval
    # (start = end = now), the next run gets the same date, and Airflow
    # refuses it as a duplicate, so the watching stops after one run.
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    # One run at a time: @continuous needs it, and DuckDB lets one process
    # write to its file at a time.
    max_active_runs=1,
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(seconds=30)},
    tags=["uploads"],
)
def watch_uploads():
    # reschedule: between looks the sensor gives its worker slot back instead
    # of sleeping in it. After an hour with nothing new it gives up quietly
    # (soft_fail: skipped, not failed), and the next run starts a fresh one.
    @task.sensor(poke_interval=30, mode="reschedule", timeout=3600, soft_fail=True)
    def new_uploads() -> PokeReturnValue:
        # Settings are read here, not at import: a wrong one fails this task
        # with a clear message instead of hiding the whole DAG.
        files = list_table_files(filestore_root(os.environ))
        rules = fetch_rules(
            os.environ["GROUPING_RULES_URL"], os.environ["PIPELINE_API_TOKEN"]
        )
        processed = processed_files(DUCKDB_PATH)
        # Here, not in a task of its own: the sensor runs while no group_file
        # does, so it is the one writer of DuckDB at this moment.
        try:
            gone = forget_removed(DUCKDB_PATH, files, rules, processed)
        except duckdb.Error:
            # Cleanup can wait for the next look; new files must not.
            log.warning("Could not drop old results", exc_info=True)
        else:
            if gone:
                log.info("Results with no saved rule dropped: %s", gone)
        todo = pending(files, rules, processed)
        return PokeReturnValue(is_done=bool(todo), xcom_value=todo)

    # One file at a time, again because of the single DuckDB writer.
    @task(max_active_tis_per_dagrun=1, retries=0)
    def group_file(item: dict) -> int:
        source, mtime_ms, group_by = item["path"], item["mtime_ms"], item["group_by"]
        rule_id = item["rule_id"]
        aggregations = item.get("aggregations", [])
        revision = item.get("revision", 0)
        try:
            path = resolve_upload(filestore_root(os.environ), source)
            schema = file_schema(path)
            column = pick_group_column(schema, group_by or None)
            checked = check_aggregations(schema, aggregations)
            return save_groups(
                DUCKDB_PATH,
                # A string, not a Path: Path would fold the // of s3://.
                path,
                source,
                column,
                rule_id=rule_id,
                mtime_ms=mtime_ms,
                group_by=group_by,
                aggregations=checked,
                revision=revision,
            )
        except (UploadError, duckdb.Error) as error:
            # A missing column or a broken file will not mend by itself: the
            # file is marked failed and waits for a new upload or for its
            # grouping to be saved again. The task still
            # goes red, so the failure shows in the UI.
            mark_failed(
                DUCKDB_PATH,
                source,
                mtime_ms,
                group_by,
                aggregations,
                str(error),
                revision,
                rule_id,
            )
            raise UploadError(f"{source}: {error}") from error

    group_file.expand(item=new_uploads())


watch_uploads()
