"""Which uploads go to the grouping in Airflow."""

import io

import duckdb
import pytest
from botocore.exceptions import EndpointConnectionError

from files import pipeline
from files.storage import StorageError


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
    with pytest.raises(pipeline.SchemaError) as caught:
        pipeline.file_schema(FakeStorage({"a.txt": b"x"}), "a.txt")
    assert str(caught.value) == "Not a table file."


def test_duckdb_reads_a_copy_with_the_original_extension(monkeypatch):
    read = []
    real_connect = pipeline.duckdb.connect

    class Spy:
        def __enter__(self):
            self.con = real_connect()
            return self

        def __exit__(self, *exc):
            self.con.close()
            return False

        def execute(self, sql, params):
            read.append(params[0])
            return self.con.execute(sql, params)

    monkeypatch.setattr(pipeline.duckdb, "connect", lambda: Spy())

    pipeline.file_schema(FakeStorage({"r/Sales.CSV": b"a\n1\n"}), "r/Sales.CSV")

    assert read[0].endswith(".csv")


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


class FailingStorage:
    """A storage that cannot hand out the file: S3 down, file just deleted."""

    def __init__(self, error):
        self.error = error

    def open(self, path):
        raise self.error


@pytest.mark.parametrize(
    "error",
    [
        StorageError("File not found."),
        OSError("Connection reset"),
        EndpointConnectionError(endpoint_url="http://localstack:4566"),
    ],
)
def test_schema_of_an_unreadable_file_is_a_schema_error(error):
    with pytest.raises(pipeline.SchemaError) as caught:
        pipeline.file_schema(FailingStorage(error), "seo.csv")

    assert str(caught.value)


def test_duckdb_error_with_no_message_still_explains(monkeypatch):
    class Silent:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, *args):
            raise duckdb.Error("")

    monkeypatch.setattr(pipeline.duckdb, "connect", lambda: Silent())

    with pytest.raises(pipeline.SchemaError) as caught:
        pipeline.file_schema(FakeStorage({"a.csv": b"x\n1\n"}), "a.csv")
    assert str(caught.value) == "DuckDB cannot read the file."


def test_storage_error_with_no_message_still_explains():
    with pytest.raises(pipeline.SchemaError) as caught:
        pipeline.file_schema(FailingStorage(StorageError("")), "seo.csv")
    assert str(caught.value) == "The file could not be read."


def test_broken_aggregations_are_described_without_failing():
    broken = [{"op": "sum"}, "sum(clicks)", {"op": "avg", "column": "ctr"}]

    assert pipeline.describe_aggregations(broken) == "avg(ctr)"
