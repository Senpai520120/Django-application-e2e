"""The storage contract.

The very same set of checks runs twice: against the local disk and against S3
(through moto). If the two implementations ever drift apart, this shows it.
"""

import boto3
import pytest
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.uploadedfile import SimpleUploadedFile
from moto import mock_aws

from files.storage import LocalFileStorage, S3FileStorage, StorageError

BUCKET = "test-file-manager"
REGION = "eu-central-1"


def upload(name: str, content: bytes = b"hello") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content)


@pytest.fixture
def local_storage(tmp_path):
    return LocalFileStorage(tmp_path / "root")


@pytest.fixture
def s3_storage(settings, monkeypatch):
    for variable in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SECURITY_TOKEN",
        "AWS_SESSION_TOKEN",
    ):
        monkeypatch.setenv(variable, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)

    settings.AWS_STORAGE_BUCKET_NAME = BUCKET
    settings.AWS_S3_REGION_NAME = REGION
    settings.AWS_ACCESS_KEY_ID = "testing"
    settings.AWS_SECRET_ACCESS_KEY = "testing"
    settings.AWS_S3_ENDPOINT_URL = None

    with mock_aws():
        boto3.client("s3", region_name=REGION).create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": REGION},
        )
        yield S3FileStorage(location="filemanager")


@pytest.fixture(params=["local", "s3"])
def storage(request):
    """Both backends behind one name, so the tests below are written once."""
    return request.getfixturevalue(f"{request.param}_storage")


def test_root_is_empty_at_start(storage):
    assert storage.list_dir() == []
    assert storage.exists("") is True
    assert storage.is_dir("") is True


def test_make_dir_and_list(storage):
    storage.make_dir("docs")

    entries = storage.list_dir()

    assert [(entry.name, entry.is_dir) for entry in entries] == [("docs", True)]
    assert storage.is_dir("docs") is True
    assert storage.exists("docs") is True


def test_nested_dirs(storage):
    storage.make_dir("docs")
    storage.make_dir("docs/2024")

    assert [entry.name for entry in storage.list_dir("docs")] == ["2024"]


def test_duplicate_dir_is_rejected(storage):
    storage.make_dir("docs")

    with pytest.raises(StorageError):
        storage.make_dir("docs")


def test_save_and_read_file(storage):
    storage.save("notes.txt", upload("notes.txt", b"content"))

    entries = storage.list_dir()
    assert [(entry.name, entry.is_dir) for entry in entries] == [("notes.txt", False)]
    assert storage.size("notes.txt") == len(b"content")

    with storage.open("notes.txt") as handle:
        assert handle.read() == b"content"


def test_duplicate_file_is_rejected(storage):
    storage.save("notes.txt", upload("notes.txt"))

    with pytest.raises(StorageError):
        storage.save("notes.txt", upload("notes.txt"))


def test_file_inside_dir(storage):
    storage.make_dir("docs")
    storage.save("docs/notes.txt", upload("notes.txt", b"inner"))

    entries = storage.list_dir("docs")

    assert [entry.name for entry in entries] == ["notes.txt"]
    assert entries[0].path == "docs/notes.txt"
    assert entries[0].size == len(b"inner")


def test_dirs_are_listed_before_files(storage):
    storage.save("a-file.txt", upload("a-file.txt"))
    storage.make_dir("z-dir")

    assert [entry.name for entry in storage.list_dir()] == ["z-dir", "a-file.txt"]


def test_rename_file(storage):
    storage.save("old.txt", upload("old.txt", b"data"))

    new_path = storage.rename("old.txt", "new.txt")

    assert new_path == "new.txt"
    assert storage.exists("new.txt") is True
    assert storage.exists("old.txt") is False
    with storage.open("new.txt") as handle:
        assert handle.read() == b"data"


def test_rename_dir_with_content(storage):
    storage.make_dir("docs")
    storage.save("docs/notes.txt", upload("notes.txt", b"inner"))

    storage.rename("docs", "archive")

    assert storage.exists("docs") is False
    assert storage.is_dir("archive") is True
    assert [entry.name for entry in storage.list_dir("archive")] == ["notes.txt"]


def test_rename_into_existing_name_is_rejected(storage):
    storage.save("one.txt", upload("one.txt"))
    storage.save("two.txt", upload("two.txt"))

    with pytest.raises(StorageError):
        storage.rename("one.txt", "two.txt")


def test_delete_file(storage):
    storage.save("notes.txt", upload("notes.txt"))

    storage.delete("notes.txt")

    assert storage.exists("notes.txt") is False
    assert storage.list_dir() == []


def test_delete_dir_is_recursive(storage):
    storage.make_dir("docs")
    storage.make_dir("docs/2024")
    storage.save("docs/notes.txt", upload("notes.txt"))
    storage.save("docs/2024/report.txt", upload("report.txt"))

    storage.delete("docs")

    assert storage.exists("docs") is False
    assert storage.list_dir() == []


def test_root_cannot_be_deleted_or_renamed(storage):
    with pytest.raises(StorageError):
        storage.delete("")

    with pytest.raises(StorageError):
        storage.rename("", "anything")


def test_missing_paths_report_errors(storage):
    with pytest.raises(StorageError):
        storage.list_dir("nope")

    with pytest.raises(StorageError):
        storage.open("nope.txt")

    with pytest.raises(StorageError):
        storage.delete("nope.txt")

    with pytest.raises(StorageError):
        storage.size("nope.txt")


@pytest.mark.parametrize(
    "path", ["../escape", "../../etc/passwd", "/etc/passwd", "docs/../../escape"]
)
def test_storage_api_rejects_traversal(storage, path):
    """Even bypassing the forms: the storage itself must not leave the root."""
    with pytest.raises(SuspiciousFileOperation):
        storage.make_dir(path)

    with pytest.raises(SuspiciousFileOperation):
        storage.save(path, upload("x.txt"))

    with pytest.raises(SuspiciousFileOperation):
        storage.delete(path)


def test_total_size_counts_all_files(storage):
    storage.make_dir("docs")
    storage.save("a.txt", upload("a.txt", b"12345"))
    storage.save("docs/b.txt", upload("b.txt", b"123"))

    assert storage.total_size() == 8


def test_local_storage_blocks_symlink_escape(tmp_path):
    """A symlink outwards is the only way around the lexical path check."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")

    root = tmp_path / "root"
    root.mkdir()
    link = root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("no permission to create symlinks")

    storage = LocalFileStorage(root)

    with pytest.raises(SuspiciousFileOperation):
        storage.list_dir("link")
