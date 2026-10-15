"""Fixtures: what a test needs before it starts, and the cleanup after it.

pytest finds this file by itself. A test asks for a fixture just by naming it
as an argument:

    def test_something(admin_page):   # pytest runs the admin_page fixture first
        ...

`page` and `new_context` come from the pytest-playwright plugin:
    page         a fresh browser tab, nobody signed in
    new_context  makes one more separate browser (own cookies, own session)

A fixture with `yield` works in two halves: the code before `yield` prepares,
the test runs, then the code after `yield` cleans up, even if the test failed.
"""

from pathlib import Path

import pytest
from playwright.sync_api import Page

import config
from config import User
from helpers import sign_in, unique_name
from pages.files_page import FilesPage
from pages.user_create_page import UserCreatePage
from pages.users_page import UsersPage

# --- signed-in browser tabs ---


@pytest.fixture
def admin_page(page: Page) -> Page:
    """A browser tab signed in as demo_admin."""
    return sign_in(page, config.ADMIN)


@pytest.fixture
def user_page(page: Page) -> Page:
    """A browser tab signed in as demo_user (no admin rights)."""
    return sign_in(page, config.REGULAR_USER)


@pytest.fixture
def admin_browser(new_context) -> Page:
    """A second, separate browser signed in as demo_admin.

    For tests where the test's own tab is signed in as somebody else:
    for example, demo_user tries something in `user_page` while the admin
    checks the result here.
    """
    return sign_in(new_context().new_page(), config.ADMIN)


# --- a fresh user for tests that change roles or switch a user off ---


@pytest.fixture
def new_user(admin_browser: Page):
    """Create a brand-new user through the panel, give it to the test.

    Why not use demo_user? If a test changes demo_user and then fails,
    demo_user stays broken and the next tests fail too. A new user per test
    keeps every test independent.

    The user is created in the separate admin browser, so the test's
    own `page` / `admin_page` stays untouched.
    """
    user = User(unique_name("user"), config.NEW_USER_PASSWORD)
    UserCreatePage(admin_browser).open().create_user(user.username, user.password)

    yield user

    # Cleanup. The panel cannot delete users, so we switch the user off:
    # then nobody can sign in with this test account.
    users_page = UsersPage(admin_browser).open()
    users_page.search(user.username)
    if users_page.deactivate_button(user.username).count() > 0:
        users_page.deactivate(user.username)


# --- file manager ---


@pytest.fixture
def files_page(admin_page: Page) -> FilesPage:
    """The file manager, signed in as admin, opened at the root folder."""
    return FilesPage(admin_page).open()


@pytest.fixture
def workspace(files_page: FilesPage):
    """An empty folder of this test's own, already opened.

    Every file test works inside its own folder, so tests never see each
    other's files. After the test the whole folder is deleted.
    """
    folder = unique_name("workspace")
    files_page.create_folder(folder)
    files_page.open_folder(folder)

    yield folder

    files_page.open()
    if files_page.entry(folder).count() > 0:
        files_page.delete(folder)


@pytest.fixture
def make_file(tmp_path: Path):
    """Write a text file to a temporary folder and return its path.

    `tmp_path` is a built-in pytest fixture: a fresh temporary folder
    that pytest removes by itself.

        report = make_file("report.txt", "some text")
    """

    def _make_file(name: str, content: str = "test content") -> Path:
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        return path

    return _make_file
