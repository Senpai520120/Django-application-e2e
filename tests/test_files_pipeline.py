"""Which uploads go to the grouping in Airflow."""

import io

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


class FakeStorage:
    """Just open(): file_schema needs nothing else from a storage."""

    def __init__(self, files):
        self.files = files

    def open(self, path):
        return io.BytesIO(self.files[path])


def test_schema_has_names_and_types():
    storage = FakeStorage({"r/sales.csv": b"category,qty,price\nbooks,3,12.5\n"})

    assert pipeline.file_schema(storage, "r/sales.csv") == [
        ("category", "VARCHAR"),
        ("qty", "BIGINT"),
        ("price", "DOUBLE"),
    ]


def test_schema_of_a_broken_file_is_a_schema_error():
    storage = FakeStorage({"x.parquet": b"not parquet"})

    with pytest.raises(pipeline.SchemaError):
        pipeline.file_schema(storage, "x.parquet")


def test_schema_only_for_table_files():
    with pytest.raises(pipeline.SchemaError):
        pipeline.file_schema(FakeStorage({"a.txt": b"x"}), "a.txt")


@pytest.mark.parametrize(
    ("type_", "expected"),
    [
        ("BIGINT", True),
        ("double", True),
        ("DECIMAL(10,2)", True),
        ("VARCHAR", False),
        ("DATE", False),
        ("BOOLEAN", False),
    ],
)
def test_number_types(type_, expected):
    assert pipeline.is_numeric(type_) is expected
