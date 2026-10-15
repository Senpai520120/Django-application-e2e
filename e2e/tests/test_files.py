"""File manager: files.

Every test gets its own empty folder from the `workspace` fixture
and works inside it. Test files are made on the fly with `make_file`.
"""

from playwright.sync_api import Page, expect

import config
from helpers import unique_name
from pages.files_page import FilesPage


def test_28_upload_file_with_cyrillic_name(files_page: FilesPage, workspace, make_file):
    """TC-28: an uploaded file appears in the list; a non-English name is kept."""
    name = f"{unique_name('отчёт')}.txt"

    files_page.upload(make_file(name, "report contents"))

    expect(files_page.status_message).to_contain_text("Uploaded files: 1.")
    expect(files_page.entry(name)).to_be_visible()
    expect(files_page.entry_row(name)).to_contain_text("file")


def test_29_upload_several_files_at_once(files_page: FilesPage, workspace, make_file):
    """TC-29: two files chosen together are both uploaded."""
    first = make_file("first.txt", "one")
    second = make_file("second.txt", "two")

    files_page.upload(first, second)

    expect(files_page.status_message).to_contain_text("Uploaded files: 2.")
    expect(files_page.entry("first.txt")).to_be_visible()
    expect(files_page.entry("second.txt")).to_be_visible()


def test_30_download_returns_same_file(files_page: FilesPage, workspace, make_file):
    """TC-30: a downloaded file has the same name and content as the uploaded one."""
    files_page.upload(make_file("download_me.txt", "useful payload"))

    # Start waiting for the download first, then click the file name.
    with files_page.page.expect_download() as download_info:
        files_page.entry("download_me.txt").click()
    download = download_info.value

    assert download.suggested_filename == "download_me.txt"
    with open(download.path(), encoding="utf-8") as downloaded:
        assert downloaded.read() == "useful payload"


def test_31_rename_file(files_page: FilesPage, workspace, make_file):
    """TC-31: a renamed file shows only under its new name."""
    files_page.upload(make_file("before.txt"))

    files_page.rename("before.txt", "after.txt")

    expect(files_page.entry("after.txt")).to_be_visible()
    expect(files_page.entry("before.txt")).to_have_count(0)


def test_32_delete_file_after_confirmation(files_page: FilesPage, workspace, make_file):
    """TC-32: a file is deleted after confirming."""
    files_page.upload(make_file("delete_me.txt"))

    files_page.delete("delete_me.txt")

    expect(files_page.status_message).to_contain_text("Deleted: delete_me.txt.")
    expect(files_page.entry("delete_me.txt")).to_have_count(0)


def test_33_file_over_size_limit_is_rejected(
    files_page: FilesPage, workspace, tmp_path
):
    """TC-33: a file one byte bigger than the limit is refused with a clear message."""
    big_file = tmp_path / "too_big.bin"
    big_file.write_bytes(b"0" * (config.MAX_FILE_SIZE + 1))

    files_page.upload(big_file)

    expect(files_page.status_message).to_contain_text("is larger than the allowed")
    expect(files_page.entry("too_big.bin")).to_have_count(0)


def test_34_file_with_taken_name_is_not_overwritten(
    files_page: FilesPage, workspace, tmp_path
):
    """TC-34: uploading a file with an existing name keeps the old file."""
    first_version = tmp_path / "v1" / "same_name.txt"
    second_version = tmp_path / "v2" / "same_name.txt"
    first_version.parent.mkdir()
    second_version.parent.mkdir()
    first_version.write_text("first version", encoding="utf-8")
    second_version.write_text("second version", encoding="utf-8")
    files_page.upload(first_version)

    files_page.upload(second_version)

    expect(files_page.status_message).to_contain_text("already exists")
    with files_page.page.expect_download() as download_info:
        files_page.entry("same_name.txt").click()
    with open(download_info.value.path(), encoding="utf-8") as downloaded:
        assert downloaded.read() == "first version"


def test_41_file_exactly_at_size_limit_is_accepted(
    files_page: FilesPage, workspace, tmp_path
):
    """TC-41: a file exactly as big as the limit is uploaded.

    Together with TC-33 (limit + 1 byte is refused) this checks both sides
    of the limit.
    """
    file_at_limit = tmp_path / "exactly_limit.bin"
    file_at_limit.write_bytes(b"0" * config.MAX_FILE_SIZE)

    files_page.upload(file_at_limit)

    expect(files_page.status_message).to_contain_text("Uploaded files: 1.")
    expect(files_page.entry("exactly_limit.bin")).to_be_visible()


def test_42_path_outside_storage_is_refused(user_page: Page):
    """TC-42: a folder path that climbs out of the storage ("../..") is refused.

    The request goes straight to the server with the user's session.
    """
    response = user_page.request.get("/files/?path=../..")

    assert response.status == 400
    assert "<h1>Files</h1>" not in response.text()  # no file list is shown
