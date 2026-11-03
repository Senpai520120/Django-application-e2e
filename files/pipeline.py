"""Sending uploaded CSV files to Airflow for processing.

The app only asks Airflow to start the process_upload DAG for a file; the
reading and grouping happen there (airflow/dags/process_upload.py), so an
upload never waits for them and keeps working while Airflow is down.
"""

import requests
from django.conf import settings

TIMEOUT = 5

DAG_ID = "process_upload"


class ProcessingUnavailable(Exception):
    """Airflow did not answer, or refused to start the run."""


def processing_enabled() -> bool:
    return bool(settings.AIRFLOW_API_URL)


def should_process(name: str) -> bool:
    return processing_enabled() and name.lower().endswith(".csv")


def access_token() -> str:
    # A token per upload: uploads are rare, and an expired one is never kept.
    response = requests.post(
        f"{settings.AIRFLOW_API_URL}/auth/token",
        json={
            "username": settings.AIRFLOW_USERNAME,
            "password": settings.AIRFLOW_PASSWORD,
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def trigger_processing(path: str) -> str:
    """Start a run for the file at `path` in the file manager; returns its id."""
    try:
        response = requests.post(
            f"{settings.AIRFLOW_API_URL}/api/v2/dags/{DAG_ID}/dagRuns",
            headers={"Authorization": f"Bearer {access_token()}"},
            # No logical date: the run is not tied to a schedule interval.
            json={"logical_date": None, "conf": {"path": path}},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json()["dag_run_id"]
    except (requests.RequestException, ValueError, KeyError) as error:
        raise ProcessingUnavailable(str(error)) from error
