"""File manager: folders.

Every test gets its own empty folder from the `workspace` fixture
and works inside it.
"""

from playwright.sync_api import expect

from helpers import unique_name
from pages.files_page import FilesPage


def test_23_create_nested_folder_and_go_back_by_breadcrumbs(
    files_page: FilesPage, workspace
):
    """TC-23: create a folder, open it, and come back through the breadcrumbs."""
    nested = unique_name("nested")

    files_page.create_folder(nested)
    expect(files_page.entry(nested)).to_be_visible()

    files_page.open_folder(nested)
    expect(files_page.current_folder).to_have_text(nested)
    expect(files_page.empty_folder_text).to_be_visible()

    files_page.breadcrumb(workspace).click()
    expect(files_page.current_folder).to_have_text(workspace)
    expect(files_page.entry(nested)).to_be_visible()

    files_page.breadcrumb("Root").click()
    expect(files_page.current_folder).to_have_text("Root")
    expect(files_page.entry(workspace)).to_be_visible()


def test_24_folder_with_taken_name_is_not_created_twice(
    files_page: FilesPage, workspace
):
    """TC-24: a second folder with the same name is refused."""
    name = unique_name("folder")
    files_page.create_folder(name)

    files_page.create_folder(name)

    expect(files_page.status_message).to_contain_text("already exists")
    expect(files_page.entry(name)).to_have_count(1)


def test_25_cancelling_folder_deletion_keeps_folder(files_page: FilesPage, workspace):
    """TC-25: "Cancel" on the delete confirmation keeps the folder."""
    name = unique_name("folder")
    files_page.create_folder(name)

    files_page.start_delete(name)
    files_page.cancel_delete_link.click()

    expect(files_page.entry(name)).to_be_visible()


def test_26_deleting_folder_removes_its_contents(
    files_page: FilesPage, workspace, make_file
):
    """TC-26: a folder with a file inside is deleted after a warning."""
    folder = unique_name("folder")
    files_page.create_folder(folder)
    files_page.open_folder(folder)
    files_page.upload(make_file("inside.txt"))
    expect(files_page.entry("inside.txt")).to_be_visible()

    files_page.open_folder_by_path(workspace)
    files_page.start_delete(folder)
    expect(files_page.folder_contents_warning).to_be_visible()
    files_page.confirm_delete_button.click()

    expect(files_page.status_message).to_contain_text(f"Deleted: {folder}.")
    expect(files_page.entry(folder)).to_have_count(0)


def test_27_rename_folder(files_page: FilesPage, workspace):
    """TC-27: a renamed folder shows only under its new name."""
    old_name = unique_name("before")
    new_name = unique_name("after")
    files_page.create_folder(old_name)

    files_page.rename(old_name, new_name)

    expect(files_page.status_message).to_contain_text(f"Renamed to {new_name}.")
    expect(files_page.entry(new_name)).to_be_visible()
    expect(files_page.entry(old_name)).to_have_count(0)
