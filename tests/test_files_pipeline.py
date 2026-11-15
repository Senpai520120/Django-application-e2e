"""Which uploads go to the grouping in Airflow."""

import pytest

from files import pipeline


@pytest.fixture
def pipeline_on(settings):
    settings.PIPELINE_API_TOKEN = "token"


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
def test_only_table_files_are_processed(pipeline_on, name, expected):
    assert pipeline.should_process(name) is expected


def test_nothing_is_processed_without_the_token(settings):
    settings.PIPELINE_API_TOKEN = ""

    assert pipeline.should_process("sales.csv") is False
