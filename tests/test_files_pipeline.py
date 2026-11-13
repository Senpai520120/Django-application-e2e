"""Sending uploads to Airflow: what is asked for, and what a failure becomes."""

import pytest
import requests

from files import pipeline

AIRFLOW = "http://airflow.test"


class FakeResponse:
    def __init__(self, body, status=200):
        self.body = body
        self.status_code = status

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


@pytest.fixture
def airflow(settings):
    settings.AIRFLOW_API_URL = AIRFLOW
    settings.AIRFLOW_USERNAME = "django"
    settings.AIRFLOW_PASSWORD = "secret"


@pytest.fixture
def calls(monkeypatch):
    """Every requests.post as (url, kwargs); answers like a working Airflow."""
    seen = []

    def fake_post(url, **kwargs):
        seen.append((url, kwargs))
        if url.endswith("/auth/token"):
            return FakeResponse({"access_token": "jwt"}, status=201)
        return FakeResponse({"dag_run_id": "manual__1"})

    monkeypatch.setattr(pipeline.requests, "post", fake_post)
    return seen


def test_trigger_gets_a_token_then_starts_the_dag(airflow, calls):
    run_id = pipeline.trigger_processing("reports/sales.csv")

    assert run_id == "manual__1"
    (token_url, token_call), (run_url, run_call) = calls
    assert token_url == f"{AIRFLOW}/auth/token"
    assert token_call["json"] == {"username": "django", "password": "secret"}
    assert run_url == f"{AIRFLOW}/api/v2/dags/process_upload/dagRuns"
    assert run_call["headers"] == {"Authorization": "Bearer jwt"}
    assert run_call["json"]["conf"] == {"path": "reports/sales.csv"}


def test_refused_token_becomes_processing_unavailable(airflow, monkeypatch):
    monkeypatch.setattr(
        pipeline.requests, "post", lambda url, **kwargs: FakeResponse({}, status=401)
    )

    with pytest.raises(pipeline.ProcessingUnavailable):
        pipeline.trigger_processing("sales.csv")


def test_airflow_down_becomes_processing_unavailable(airflow, monkeypatch):
    def refuse(url, **kwargs):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(pipeline.requests, "post", refuse)

    with pytest.raises(pipeline.ProcessingUnavailable):
        pipeline.trigger_processing("sales.csv")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("sales.csv", True),
        ("SALES.CSV", True),
        ("sales.xlsx", True),
        ("sales.json", True),
        ("sales.parquet", True),
        ("sales.xls", False),
        ("notes.txt", False),
        ("csv", False),
    ],
)
def test_only_table_files_are_processed(airflow, name, expected):
    assert pipeline.should_process(name) is expected


def test_nothing_is_processed_without_airflow(settings):
    settings.AIRFLOW_API_URL = ""

    assert pipeline.should_process("sales.csv") is False
