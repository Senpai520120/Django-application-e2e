"""The DAG's grouping, run against a real DuckDB file."""

import os

import boto3
import duckdb
import pytest
from moto.server import ThreadedMotoServer
from upload_groups import (
    UploadError,
    file_columns,
    file_schema,
    filestore_root,
    pick_column,
    pick_group_column,
    resolve_upload,
    s3_secret,
    save_groups,
)

SALES = "category,amount\nbooks,10\ntoys,5\nbooks,7\n"


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "filestore"
    (root / "reports").mkdir(parents=True)
    (root / "reports" / "sales.csv").write_text(SALES)
    return root


def rows(db_path):
    with duckdb.connect(str(db_path)) as con:
        return con.execute(
            "SELECT source, group_column, group_value, row_count"
            " FROM upload_groups ORDER BY group_value"
        ).fetchall()


def test_groups_by_the_first_column(store, tmp_path):
    path = resolve_upload(store, "reports/sales.csv")
    column = pick_column(file_columns(path), None)

    db = tmp_path / "a.duckdb"

    assert save_groups(db, path, "reports/sales.csv", column) == 2
    assert rows(db) == [
        ("reports/sales.csv", "category", "books", 2),
        ("reports/sales.csv", "category", "toys", 1),
    ]


def test_same_file_again_replaces_its_groups(store, tmp_path):
    db = tmp_path / "a.duckdb"
    path = resolve_upload(store, "reports/sales.csv")

    save_groups(db, path, "reports/sales.csv", "category")
    save_groups(db, path, "reports/sales.csv", "category")

    assert len(rows(db)) == 2


def test_requested_column_must_exist(store):
    columns = file_columns(resolve_upload(store, "reports/sales.csv"))

    assert pick_column(columns, "amount") == "amount"
    with pytest.raises(UploadError):
        pick_column(columns, "price")


@pytest.fixture(scope="module")
def table_files(tmp_path_factory):
    """The same sales table saved in every format the DAG reads."""
    folder = tmp_path_factory.mktemp("tables")
    with duckdb.connect() as con:
        # Writing .xlsx needs the excel extension loaded; reading loads it alone.
        con.execute("INSTALL excel")
        con.execute("LOAD excel")
        con.execute(
            "CREATE TABLE sales AS SELECT * FROM (VALUES"
            " ('books', 10), ('toys', 5), ('books', 7)) t(category, amount)"
        )
        for ext, options in [
            ("csv", "FORMAT csv, HEADER true"),
            ("json", "FORMAT json, ARRAY true"),
            ("parquet", "FORMAT parquet"),
            ("xlsx", "FORMAT xlsx, HEADER true"),
        ]:
            con.execute(f"COPY sales TO '{folder / ('sales.' + ext)}' ({options})")
    return folder


@pytest.mark.parametrize(
    "name", ["sales.csv", "sales.json", "sales.parquet", "sales.xlsx"]
)
def test_every_table_format_is_grouped(table_files, tmp_path, name):
    path = resolve_upload(table_files, name)
    db = tmp_path / "a.duckdb"

    assert file_columns(path) == ["category", "amount"]
    assert save_groups(db, path, name, "category") == 2
    assert rows(db) == [(name, "category", "books", 2), (name, "category", "toys", 1)]


def test_other_files_are_refused(tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("hello")

    with pytest.raises(UploadError):
        file_columns(notes)


@pytest.mark.parametrize("path", ["../secret.csv", "/etc/passwd", "", "missing.csv"])
def test_path_must_point_to_a_file_inside_the_store(store, path):
    with pytest.raises(UploadError):
        resolve_upload(store, path)


S3_ENV = {
    "FILE_STORAGE_BACKEND": "s3",
    "AWS_STORAGE_BUCKET_NAME": "uploads",
    "FILE_MANAGER_S3_LOCATION": "filemanager",
    "AWS_S3_REGION_NAME": "us-east-1",
    "AWS_S3_ADDRESSING_STYLE": "path",
    "AWS_ACCESS_KEY_ID": "test",
    "AWS_SECRET_ACCESS_KEY": "test",
}


@pytest.fixture
def bucket(monkeypatch):
    """A real S3 endpoint (moto's server) with sales.csv where the app puts it."""
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
    server.start()
    host, port = server.get_host_and_port()
    endpoint = f"http://{host}:{port}"
    for name, value in {**S3_ENV, "AWS_S3_ENDPOINT_URL": endpoint}.items():
        monkeypatch.setenv(name, value)
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    s3.create_bucket(Bucket="uploads")
    s3.put_object(
        Bucket="uploads", Key="filemanager/reports/sales.csv", Body=SALES.encode()
    )
    yield
    server.stop()


def test_file_in_s3_is_grouped(bucket, tmp_path):
    path = resolve_upload(filestore_root(os.environ), "reports/sales.csv")
    db = tmp_path / "a.duckdb"

    assert path == "s3://uploads/filemanager/reports/sales.csv"
    assert file_columns(path) == ["category", "amount"]
    assert save_groups(db, path, "reports/sales.csv", "category") == 2
    assert rows(db) == [
        ("reports/sales.csv", "category", "books", 2),
        ("reports/sales.csv", "category", "toys", 1),
    ]


def test_missing_object_in_s3_fails_the_read(bucket):
    path = resolve_upload(filestore_root(os.environ), "reports/gone.csv")

    with pytest.raises(duckdb.Error):
        file_columns(path)


@pytest.mark.parametrize("path", ["../other/secret.csv", "/etc/passwd", ""])
def test_s3_path_must_stay_under_the_prefix(path):
    with pytest.raises(UploadError):
        resolve_upload("s3://uploads/filemanager", path)


def test_root_follows_the_app_storage_setting():
    assert filestore_root({"FILESTORE_ROOT": "/data/filestore"}) == "/data/filestore"
    assert filestore_root(S3_ENV) == "s3://uploads/filemanager"
    assert filestore_root({**S3_ENV, "FILE_MANAGER_S3_LOCATION": ""}) == "s3://uploads"
    with pytest.raises(UploadError):
        filestore_root({"FILE_STORAGE_BACKEND": "s3"})


def test_s3_secret_matches_the_app_settings():
    assert s3_secret({"FILE_STORAGE_BACKEND": "local"}) is None

    emulator = s3_secret({**S3_ENV, "AWS_S3_ENDPOINT_URL": "http://localstack:4566"})
    assert "KEY_ID 'test'" in emulator
    assert "ENDPOINT 'localstack:4566'" in emulator
    assert "USE_SSL false" in emulator
    assert "URL_STYLE 'path'" in emulator

    # No keys in the environment: an instance role, as on the EC2 deploy.
    keyless = {"FILE_STORAGE_BACKEND": "s3", "AWS_STORAGE_BUCKET_NAME": "uploads"}
    secret = s3_secret(keyless)
    assert "PROVIDER credential_chain" in secret
    assert "KEY_ID" not in secret
    assert "ENDPOINT" not in secret


def test_default_group_column_is_the_first_text_one(tmp_path):
    csv = tmp_path / "orders.csv"
    csv.write_text("id,amount,customer,city\n1,10.5,ann,Kyiv\n2,7.0,bob,Lviv\n")

    schema = file_schema(csv)

    assert [name for name, _ in schema] == ["id", "amount", "customer", "city"]
    assert pick_group_column(schema, None) == "customer"
    assert pick_group_column(schema, "") == "customer"


def test_group_column_falls_back_to_the_first_when_no_text():
    schema = [("id", "BIGINT"), ("amount", "DOUBLE")]

    assert pick_group_column(schema, None) == "id"


def test_requested_group_column_wins_and_is_checked():
    schema = [("id", "BIGINT"), ("name", "VARCHAR")]

    assert pick_group_column(schema, "id") == "id"
    with pytest.raises(UploadError, match="No column"):
        pick_group_column(schema, "nope")
    with pytest.raises(UploadError, match="no columns"):
        pick_group_column([], None)
