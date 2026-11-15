"""Uploaded table files and the grouping in Airflow.

The app never calls Airflow. It stores a GroupingRule next to each table file,
and the watch_uploads DAG (airflow/dags/watch_uploads.py) finds new files by
itself and reads their rules from the grouping-rules API.
"""

from django.conf import settings

# Formats the DAG can read; keep in step with READERS in
# airflow/dags/upload_groups.py. Other files are only stored.
TABLE_FORMATS = (".csv", ".xlsx", ".json", ".parquet")


def processing_enabled() -> bool:
    """On when Airflow has a token to read the rules with."""
    return bool(settings.PIPELINE_API_TOKEN)


def should_process(name: str) -> bool:
    return processing_enabled() and name.lower().endswith(TABLE_FORMATS)
