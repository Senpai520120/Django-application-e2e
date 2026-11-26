"""The DAG's grouping, run against a real DuckDB file."""

import io
import json
import os
from decimal import Decimal

import boto3
import duckdb
import pytest
from moto.server import ThreadedMotoServer
from upload_groups import (
    UploadError,
    aggregations_key,
    check_aggregations,
    fetch_rules,
    file_columns,
    file_schema,
    filestore_root,
    forget_removed,
    list_table_files,
    mark_failed,
    pending,
    pick_column,
    pick_group_column,
    processed_files,
    resolve_upload,
    result_columns,
    s3_secret,
    save_groups,
)

SALES = "category,amount\nbooks,10\ntoys,5\nbooks,7\n"

# The rule and the done mark every save_groups call needs; most tests do not
# look at them. The result goes to result_1.
MARK = {"rule_id": 1, "mtime_ms": 1, "group_by": ""}


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "filestore"
    (root / "reports").mkdir(parents=True)
    (root / "reports" / "sales.csv").write_text(SALES)
    return root


def table(db_path, rule_id=1):
    """(column names, rows) of a result table."""
    with duckdb.connect(str(db_path)) as con:
        cursor = con.execute(f"SELECT * FROM result_{rule_id}")
        return [column[0] for column in cursor.description], cursor.fetchall()


def rows(db_path, rule_id=1):
    return table(db_path, rule_id)[1]


def tables(db_path):
    with duckdb.connect(str(db_path)) as con:
        found = con.execute("SELECT table_name FROM duckdb_tables()").fetchall()
    return sorted(row[0] for row in found)


def test_groups_by_the_first_column(store, tmp_path):
    path = resolve_upload(store, "reports/sales.csv")
    column = pick_column(file_columns(path), None)

    db = tmp_path / "a.duckdb"

    assert save_groups(db, path, "reports/sales.csv", column, **MARK) == 2
    assert table(db) == (["category", "row_count"], [("books", 2), ("toys", 1)])


def test_same_file_again_replaces_its_groups(store, tmp_path):
    db = tmp_path / "a.duckdb"
    path = resolve_upload(store, "reports/sales.csv")

    save_groups(db, path, "reports/sales.csv", "category", **MARK)
    save_groups(db, path, "reports/sales.csv", "category", **MARK)

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
    assert save_groups(db, path, name, "category", **MARK) == 2
    assert rows(db) == [("books", 2), ("toys", 1)]


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
    assert save_groups(db, path, "reports/sales.csv", "category", **MARK) == 2
    assert rows(db) == [("books", 2), ("toys", 1)]


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


def test_table_files_are_listed_with_their_times(store):
    (store / "reports" / "q1").mkdir()
    (store / "reports" / "q1" / "B.CSV").write_text(SALES)
    (store / "notes.txt").write_text("hello")

    files = list_table_files(store)

    assert sorted(files) == ["reports/q1/B.CSV", "reports/sales.csv"]
    assert all(isinstance(mtime, int) and mtime > 0 for mtime in files.values())


def test_empty_or_missing_store_lists_nothing(tmp_path):
    assert list_table_files(tmp_path) == {}
    assert list_table_files(tmp_path / "nope") == {}


def test_files_in_s3_are_listed(bucket):
    files = list_table_files(filestore_root(os.environ))

    assert list(files) == ["reports/sales.csv"]


def rule(group_by="", aggregations=(), configured=True, revision=0, id: int | None = 1):
    return {
        "id": id,
        "group_by": group_by,
        "aggregations": list(aggregations),
        "configured": configured,
        "revision": revision,
    }


def item(path, mtime_ms=5, group_by="", aggregations=(), revision=0, rule_id=1):
    """One entry of what pending() hands on to group_file."""
    return {
        "path": path,
        "rule_id": rule_id,
        "mtime_ms": mtime_ms,
        "group_by": group_by,
        "aggregations": list(aggregations),
        "revision": revision,
    }


SUM_CLICKS = {"op": "sum", "column": "clicks"}


def test_pending_takes_only_what_changed():
    files = {
        "new.csv": 5,
        "same.csv": 5,
        "again.csv": 9,
        "column.csv": 5,
        "math.csv": 5,
        "moved.csv": 5,
    }
    rules = {
        "new.csv": rule(),
        "same.csv": rule("city", [SUM_CLICKS]),
        "again.csv": rule(),
        "column.csv": rule("country"),
        "math.csv": rule("city", [SUM_CLICKS]),
        # Deleted and uploaded again: the same name, a new rule.
        "moved.csv": rule(id=2),
    }
    processed = {
        "same.csv": (5, "city", aggregations_key([SUM_CLICKS]), 0, 1),
        "again.csv": (5, "", "[]", 0, 1),
        "column.csv": (5, "device", "[]", 0, 1),
        "math.csv": (5, "city", "[]", 0, 1),
        "deleted.csv": (5, "", "[]", 0, 1),
        "moved.csv": (5, "", "[]", 0, 1),
    }

    todo = pending(files, rules, processed)

    assert todo == [
        item("again.csv", mtime_ms=9),
        item("column.csv", group_by="country"),
        item("math.csv", group_by="city", aggregations=[SUM_CLICKS]),
        item("moved.csv", rule_id=2),
        item("new.csv"),
    ]


def test_saved_file_is_marked_done(store, tmp_path):
    db = tmp_path / "a.duckdb"
    path = resolve_upload(store, "reports/sales.csv")
    asked = [{"op": "sum", "column": "amount"}]

    save_groups(
        db,
        path,
        "reports/sales.csv",
        "category",
        rule_id=1,
        mtime_ms=7,
        group_by="",
        aggregations=asked,
    )

    done = processed_files(db)
    assert done == {"reports/sales.csv": (7, "", aggregations_key(asked), 0, 1)}
    assert (
        pending({"reports/sales.csv": 7}, {"reports/sales.csv": rule("", asked)}, done)
        == []
    )


def test_failed_file_is_taken_again_when_its_rule_is_saved_again(tmp_path):
    db = tmp_path / "a.duckdb"
    mark_failed(db, "seo.csv", 3, "device", [], "HTTP 503", revision=1, rule_id=1)
    done = processed_files(db)

    assert pending({"seo.csv": 3}, {"seo.csv": rule("device", revision=1)}, done) == []
    # The same choice saved again: a new revision, so the sensor retries.
    assert pending({"seo.csv": 3}, {"seo.csv": rule("device", revision=2)}, done) == [
        item("seo.csv", mtime_ms=3, group_by="device", revision=2)
    ]


def test_revision_is_kept_with_the_result(store, tmp_path):
    db = tmp_path / "a.duckdb"
    path = resolve_upload(store, "reports/sales.csv")

    save_groups(db, path, "reports/sales.csv", "category", **MARK, revision=4)

    assert processed_files(db) == {"reports/sales.csv": (1, "", "[]", 4, 1)}


def test_failed_file_is_not_taken_again(tmp_path):
    db = tmp_path / "a.duckdb"

    mark_failed(db, "seo.csv", 3, "price", [], "No column 'price'", rule_id=1)

    assert (
        pending({"seo.csv": 3}, {"seo.csv": rule("price")}, processed_files(db)) == []
    )
    with duckdb.connect(str(db)) as con:
        assert con.execute("SELECT status, error FROM processed_files").fetchall() == [
            ("failed", "No column 'price'")
        ]


def test_fresh_database_has_nothing_processed(tmp_path):
    assert processed_files(tmp_path / "a.duckdb") == {}


def test_database_from_before_aggregations_is_upgraded(tmp_path):
    db = tmp_path / "a.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute(
            "CREATE TABLE processed_files (source VARCHAR PRIMARY KEY,"
            " mtime_ms BIGINT NOT NULL, group_by VARCHAR NOT NULL,"
            " status VARCHAR NOT NULL, error VARCHAR,"
            " processed_at TIMESTAMP NOT NULL DEFAULT current_timestamp)"
        )
        con.execute(
            "INSERT INTO processed_files VALUES ('a.csv', 5, '', 'done', NULL, now())"
        )

    done = processed_files(db)

    # Done with no aggregations and revision 0, but with no rule id: its
    # result lived in the old long tables, so it is taken once more to get a
    # table of its own.
    assert done == {"a.csv": (5, "", "[]", 0, None)}
    assert pending({"a.csv": 5}, {"a.csv": rule()}, done) == [item("a.csv")]


def test_draft_rule_and_no_rule_make_the_file_wait():
    files = {"draft.csv": 5, "renamed.csv": 5, "chosen.csv": 5}
    rules = {"draft.csv": rule(configured=False), "chosen.csv": rule("city")}

    todo = pending(files, rules, {})

    # renamed.csv has no rule (it was a .txt): nobody chose its column, so it
    # waits like a draft instead of going by the first text column.
    assert [entry["path"] for entry in todo] == ["chosen.csv"]


def test_draft_saved_later_is_processed():
    files = {"seo.csv": 5}

    assert pending(files, {"seo.csv": rule("device", configured=False)}, {}) == []
    assert [
        item["path"] for item in pending(files, {"seo.csv": rule("device")}, {})
    ] == ["seo.csv"]


def test_rules_are_fetched_with_the_token(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout):
        seen["auth"] = request.get_header("Authorization")
        seen["timeout"] = timeout
        body = [
            {
                "id": 7,
                "path": "seo.csv",
                "group_by": "device",
                "aggregations": [SUM_CLICKS],
                "revision": 3,
            },
            {"id": 8, "path": "a.csv", "group_by": ""},
            {"id": 9, "path": "new.csv", "group_by": "", "configured": False},
        ]
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    rules = fetch_rules("http://web:8000/files/api/grouping-rules/", "tok")

    assert rules == {
        "seo.csv": rule("device", [SUM_CLICKS], revision=3, id=7),
        "a.csv": rule(id=8),
        "new.csv": rule(configured=False, id=9),
    }
    assert seen == {"auth": "Bearer tok", "timeout": 5}


ORDERS = "city,amount,qty,note\nKyiv,10.5,1,a\nLviv,4,2,\nKyiv,5,3,b\n"


@pytest.fixture
def orders(tmp_path):
    csv = tmp_path / "orders.csv"
    csv.write_text(ORDERS)
    return csv


def test_aggregations_are_computed_per_group(orders, tmp_path):
    db = tmp_path / "a.duckdb"
    asked = check_aggregations(
        file_schema(orders),
        [
            {"op": "sum", "column": "amount"},
            {"op": "avg", "column": "qty"},
            {"op": "min", "column": "amount"},
            {"op": "max", "column": "qty"},
            {"op": "count", "column": "note"},
        ],
    )

    save_groups(db, orders, "orders.csv", "city", **MARK, aggregations=asked)

    columns, found = table(db)
    assert columns == [
        "city",
        "row_count",
        "sum_amount",
        "avg_qty",
        "min_amount",
        "max_qty",
        "count_note",
    ]
    assert found == [
        ("Kyiv", 2, 15.5, 2.0, 5.0, 3, 2),
        # count skips empty values, like SQL's count(column).
        ("Lviv", 1, 4.0, 2.0, 4.0, 2, 0),
    ]


def test_new_aggregations_replace_the_old_ones(orders, tmp_path):
    db = tmp_path / "a.duckdb"
    schema = file_schema(orders)
    first = check_aggregations(schema, [{"op": "sum", "column": "amount"}])
    second = check_aggregations(schema, [{"op": "max", "column": "qty"}])

    save_groups(db, orders, "orders.csv", "city", **MARK, aggregations=first)
    save_groups(db, orders, "orders.csv", "city", **MARK, aggregations=second)

    assert table(db) == (
        ["city", "row_count", "max_qty"],
        [("Kyiv", 2, 3), ("Lviv", 1, 2)],
    )


def test_no_aggregations_give_only_the_counts(orders, tmp_path):
    db = tmp_path / "a.duckdb"

    save_groups(db, orders, "orders.csv", "city", **MARK)

    assert table(db)[0] == ["city", "row_count"]


@pytest.mark.parametrize(
    ("asked", "message"),
    [
        ({"op": "sum", "column": "price"}, "No column 'price'"),
        ({"op": "sum", "column": "city"}, "not a number"),
        ({"op": "median", "column": "qty"}, "Unknown aggregation"),
        ({"op": "sum); DROP TABLE x; --", "column": "qty"}, "Unknown aggregation"),
    ],
)
def test_bad_aggregations_are_refused(orders, asked, message):
    with pytest.raises(UploadError, match=message):
        check_aggregations(file_schema(orders), [asked])


def test_count_takes_any_column(orders):
    asked = [{"op": "count", "column": "city"}]

    assert check_aggregations(file_schema(orders), asked) == asked


def test_column_names_are_quoted(tmp_path):
    csv = tmp_path / "odd.csv"
    csv.write_text('kind,"total ""net"""\na,1\na,2\n')
    db = tmp_path / "a.duckdb"
    asked = check_aggregations(
        file_schema(csv), [{"op": "sum", "column": 'total "net"'}]
    )

    save_groups(db, csv, "odd.csv", "kind", **MARK, aggregations=asked)

    assert table(db) == (["kind", "row_count", 'sum_total "net"'], [("a", 2, 3)])


def test_decimal_column_counts_as_a_number(tmp_path):
    parquet = tmp_path / "prices.parquet"
    with duckdb.connect() as con:
        con.execute(
            "COPY (SELECT * FROM (VALUES ('a', 1.25::DECIMAL(10,2)),"
            " ('a', 2.50::DECIMAL(10,2))) t(kind, price))"
            f" TO '{parquet}' (FORMAT parquet)"
        )
    schema = file_schema(parquet)
    assert dict(schema)["price"].startswith("DECIMAL")
    db = tmp_path / "a.duckdb"

    asked = check_aggregations(schema, [{"op": "sum", "column": "price"}])
    save_groups(db, parquet, "prices.parquet", "kind", **MARK, aggregations=asked)

    assert rows(db) == [("a", 2, Decimal("3.75"))]


# --- a broken rule fails one file, not the sensor ---


@pytest.mark.parametrize(
    "broken", [[{"op": "sum"}], ["sum(clicks)"], {"op": "sum", "column": "x"}]
)
def test_broken_rule_does_not_stop_the_other_files(broken):
    files = {"bad.csv": 5, "good.csv": 5}
    rules = {"bad.csv": rule(aggregations=()), "good.csv": rule("city")}
    rules["bad.csv"]["aggregations"] = broken

    todo = pending(files, rules, {})

    # Both are handed on; group_file then fails bad.csv alone.
    assert [entry["path"] for entry in todo] == ["bad.csv", "good.csv"]
    with pytest.raises(UploadError):
        check_aggregations([("x", "BIGINT")], todo[0]["aggregations"])


# --- results of renamed and deleted files are dropped ---


def results(db, *sources):
    """Save the same groups under each source, the n-th as result_<n>."""
    for rule_id, source in enumerate(sources, 1):
        save_groups(
            db,
            db.parent / "orders.csv",
            source,
            "city",
            rule_id=rule_id,
            mtime_ms=1,
            group_by="",
        )
    return processed_files(db)


def sources_left(db):
    """(result tables, sources in processed_files) still in the database."""
    with duckdb.connect(str(db)) as con:
        done = con.execute("SELECT source FROM processed_files").fetchall()
    results = [name for name in tables(db) if name.startswith("result_")]
    return results, sorted(row[0] for row in done)


def test_results_without_a_saved_rule_are_dropped(orders, tmp_path):
    db = tmp_path / "a.duckdb"
    processed = results(db, "kept.csv", "old.csv", "again.csv", "legacy.csv")
    files = {"kept.csv": 1, "again.csv": 1, "legacy.csv": 1}
    rules = {
        "kept.csv": rule("city", id=1),
        # Deleted and uploaded again under the same name: a draft once more.
        "again.csv": rule(configured=False, id=5),
    }
    # old.csv: deleted or renamed, no file and no rule. legacy.csv: a file
    # with no rule, which the list shows as waiting.

    gone = forget_removed(db, files, rules, processed)

    assert gone == ["again.csv", "legacy.csv", "old.csv"]
    assert sources_left(db) == (["result_1"], ["kept.csv"])


def test_empty_listing_deletes_nothing_that_has_a_rule(orders, tmp_path):
    db = tmp_path / "a.duckdb"
    processed = results(db, "a.csv", "b.csv")
    rules = {"a.csv": rule("city", id=1), "b.csv": rule("city", id=2)}

    # An unmounted volume or S3 not answering lists nothing at all.
    assert forget_removed(db, {}, rules, processed) == []
    assert sources_left(db) == (["result_1", "result_2"], ["a.csv", "b.csv"])


def test_file_removed_behind_the_apps_back_is_dropped(orders, tmp_path):
    db = tmp_path / "a.duckdb"
    processed = results(db, "a.csv", "b.csv")
    rules = {"a.csv": rule("city", id=1), "b.csv": rule("city", id=2)}

    # b.csv was deleted in the S3 console: its rule is still there, but a
    # listing that is not empty no longer has it.
    assert forget_removed(db, {"a.csv": 1}, rules, processed) == ["b.csv"]
    assert sources_left(db) == (["result_1"], ["a.csv"])


def test_forget_removed_does_not_open_the_database_when_nothing_is_gone(
    tmp_path, monkeypatch
):
    def no_connection(*args):
        raise AssertionError("no write needed")

    monkeypatch.setattr("upload_groups.connect", no_connection)

    assert (
        forget_removed(
            tmp_path / "a.duckdb", {"a.csv": 1}, {"a.csv": rule()}, {"a.csv": ()}
        )
        == []
    )


def test_sums_of_whole_numbers_are_exact(tmp_path):
    csv = tmp_path / "big.csv"
    big = 2**52 + 1
    csv.write_text(f"kind,amount\na,{big}\na,{big}\n")
    db = tmp_path / "a.duckdb"

    asked = check_aggregations(file_schema(csv), [{"op": "sum", "column": "amount"}])
    save_groups(db, csv, "big.csv", "kind", **MARK, aggregations=asked)

    # The sum keeps DuckDB's own type (HUGEINT for whole numbers), so it is
    # exact; the old long table cast every value to DOUBLE.
    assert rows(db) == [("a", 2, 2 * big)]


# --- a wide table per file ---


def test_each_file_gets_a_table_of_its_own_shape(orders, store, tmp_path):
    db = tmp_path / "a.duckdb"
    sales = resolve_upload(store, "reports/sales.csv")
    asked = check_aggregations(file_schema(orders), [{"op": "sum", "column": "qty"}])

    save_groups(db, sales, "reports/sales.csv", "category", **{**MARK, "rule_id": 3})
    save_groups(
        db, orders, "orders.csv", "city", **{**MARK, "rule_id": 4}, aggregations=asked
    )

    assert tables(db) == ["processed_files", "result_3", "result_4"]
    assert table(db, 3)[0] == ["category", "row_count"]
    assert table(db, 4)[0] == ["city", "row_count", "sum_qty"]
    with duckdb.connect(str(db)) as con:
        types = dict(
            con.execute(
                "SELECT column_name, column_type FROM (DESCRIBE result_4)"
            ).fetchall()
        )
    # The file's own types, not text and DOUBLE for everything.
    assert types == {"city": "VARCHAR", "row_count": "BIGINT", "sum_qty": "HUGEINT"}


def test_result_column_names_never_clash():
    sum_amount = {"op": "sum", "column": "amount"}

    assert result_columns("city", [sum_amount]) == ["city", "row_count", "sum_amount"]
    # A file column called row_count, grouped by.
    assert result_columns("row_count", []) == ["row_count", "row_count_2"]
    # Grouped by a column that is called like an alias; DuckDB ignores case.
    assert result_columns("Sum_Amount", [sum_amount]) == [
        "Sum_Amount",
        "row_count",
        "sum_amount_2",
    ]
    # The suffix itself taken: the next number.
    assert result_columns("row_count_2", [{"op": "count", "column": "row"}]) == [
        "row_count_2",
        "row_count",
        "count_row",
    ]
    assert result_columns("x", [sum_amount, sum_amount]) == [
        "x",
        "row_count",
        "sum_amount",
        "sum_amount_2",
    ]


def test_file_with_a_row_count_column_is_grouped(tmp_path):
    csv = tmp_path / "counts.csv"
    csv.write_text("row_count,sum_row_count\na,1\na,2\nb,5\n")
    db = tmp_path / "a.duckdb"
    asked = check_aggregations(
        file_schema(csv), [{"op": "sum", "column": "sum_row_count"}]
    )

    save_groups(db, csv, "counts.csv", "row_count", **MARK, aggregations=asked)

    assert table(db) == (
        ["row_count", "row_count_2", "sum_sum_row_count"],
        [("a", 2, 3), ("b", 1, 5)],
    )


def test_hostile_column_names_stay_names(tmp_path):
    csv = tmp_path / "evil.csv"
    csv.write_text('"k"";DROP TABLE processed_files;--",n\na,1\n')
    db = tmp_path / "a.duckdb"
    schema = file_schema(csv)
    group = schema[0][0]
    asked = check_aggregations(schema, [{"op": "sum", "column": "n"}])

    save_groups(db, csv, "evil.csv", group, **MARK, aggregations=asked)

    assert table(db) == ([group, "row_count", "sum_n"], [("a", 1, 1)])
    assert "processed_files" in tables(db)


def test_new_rule_for_the_same_name_drops_the_old_table(orders, tmp_path):
    db = tmp_path / "a.duckdb"

    save_groups(db, orders, "orders.csv", "city", **{**MARK, "rule_id": 1})
    # Deleted and uploaded again: a new rule, so a new table.
    save_groups(db, orders, "orders.csv", "city", **{**MARK, "rule_id": 2})

    assert tables(db) == ["processed_files", "result_2"]


def test_failed_file_loses_its_old_table(orders, tmp_path):
    db = tmp_path / "a.duckdb"
    save_groups(db, orders, "orders.csv", "city", **MARK)

    mark_failed(db, "orders.csv", 2, "price", [], "No column 'price'", rule_id=1)

    # The app shows the error, not the table of the rule before.
    assert tables(db) == ["processed_files"]


def test_old_long_tables_are_dropped(orders, tmp_path):
    db = tmp_path / "a.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute("CREATE TABLE upload_groups (source VARCHAR)")
        con.execute("CREATE TABLE upload_aggregates (source VARCHAR)")

    save_groups(db, orders, "orders.csv", "city", **MARK)

    assert tables(db) == ["processed_files", "result_1"]


def test_tables_that_only_look_like_results_are_left_alone(orders, tmp_path):
    db = tmp_path / "a.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute("CREATE TABLE result_notes (x INTEGER)")

    processed = results(db, "a.csv")
    forget_removed(db, {"a.csv": 1}, {}, processed)

    assert tables(db) == ["processed_files", "result_notes"]


def test_rule_without_an_id_waits():
    files = {"old.csv": 5}

    assert pending(files, {"old.csv": rule(id=None)}, {}) == []


def test_opening_waits_while_the_app_reads(tmp_path, monkeypatch):
    real_connect = duckdb.connect
    tries = []

    def busy_twice(database, *args, **kwargs):
        tries.append(database)
        if len(tries) <= 2:
            raise duckdb.IOException("Could not set lock on file: Conflicting lock")
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr("upload_groups.time.sleep", lambda seconds: None)
    monkeypatch.setattr("upload_groups.duckdb.connect", busy_twice)

    assert processed_files(tmp_path / "a.duckdb") == {}
    assert len(tries) == 3


def test_opening_gives_up_on_other_errors_and_after_the_wait(tmp_path, monkeypatch):
    def broken(database, *args, **kwargs):
        raise duckdb.IOException("Could not read the file")

    monkeypatch.setattr("upload_groups.duckdb.connect", broken)
    with pytest.raises(duckdb.IOException, match="read"):
        processed_files(tmp_path / "a.duckdb")

    def locked(database, *args, **kwargs):
        raise duckdb.IOException("Could not set lock on file")

    monkeypatch.setattr("upload_groups.duckdb.connect", locked)
    monkeypatch.setattr("upload_groups.LOCK_WAIT_SECONDS", 0)
    with pytest.raises(duckdb.IOException, match="lock"):
        processed_files(tmp_path / "a.duckdb")
