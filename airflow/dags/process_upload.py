"""Group a table file uploaded through the file manager and save it into DuckDB.

No schedule: the app triggers a run through the REST API right after a
.csv, .xlsx, .json or .parquet file is saved, with the file's path in the
run's parameters.
"""

from __future__ import annotations

import os
from pathlib import Path

from airflow.sdk import Param, dag, task
from upload_groups import file_columns, pick_column, resolve_upload, save_groups

FILESTORE_ROOT = os.environ.get("FILESTORE_ROOT", "/data/filestore")
DUCKDB_PATH = os.environ.get("DUCKDB_PATH", "/data/analytics/analytics.duckdb")


@dag(
    schedule=None,
    catchup=False,
    # DuckDB lets one process write to its file at a time.
    max_active_runs=1,
    params={
        "path": Param(type="string", description="Path inside the file manager"),
        "group_by": Param(
            None, type=["null", "string"], description="Column; the first if empty"
        ),
    },
    tags=["uploads"],
)
def process_upload():
    @task
    def locate(**context) -> dict:
        params = context["params"]
        path = resolve_upload(FILESTORE_ROOT, params["path"])
        column = pick_column(file_columns(path), params["group_by"])
        return {"path": str(path), "column": column}

    @task
    def group_and_save(found: dict, **context) -> int:
        return save_groups(
            DUCKDB_PATH,
            Path(found["path"]),
            source=context["params"]["path"],
            column=found["column"],
        )

    group_and_save(locate())


process_upload()
