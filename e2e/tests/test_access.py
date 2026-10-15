"""Who can open the admin panel and the file manager."""

import re

from playwright.sync_api import Page, expect

import config
from helpers import send_form
from pages.home_page import HomePage
from pages.user_roles_page import UserRolesPage
from pages.users_page import UsersPage

# The page Django shows when the permission check says "no".
# A missing CSRF token also gives 403, but with a different page,
# so checking this text proves which check refused the request.
ACCESS_DENIED = "403 — access denied"


def test_08_regular_user_gets_403_on_admin_panel(user_page: Page):
    """TC-08: a user without the admin role gets "access denied" on /manage/."""
    user_page.goto("/manage/")

    expect(user_page.get_by_role("heading", name=ACCESS_DENIED)).to_be_visible()


def test_09_admin_opens_admin_panel(admin_page: Page):
    """TC-09: an admin opens the user list at /manage/."""
    users_page = UsersPage(admin_page).open()

    expect(users_page.heading).to_be_visible()
    expect(users_page.row("demo_admin")).to_be_visible()


def test_10_regular_user_does_not_see_admin_links(user_page: Page):
    """TC-10: a regular user has no "Users", "Roles" and "Audit" links in the header."""
    home_page = HomePage(user_page).open()

    expect(home_page.header_link("Files")).to_be_visible()
    expect(home_page.header_link("Users")).to_have_count(0)
    expect(home_page.header_link("Roles")).to_have_count(0)
    expect(home_page.header_link("Audit")).to_have_count(0)


def test_11_anonymous_user_cannot_open_file_manager(page: Page):
    """TC-11: an anonymous user who opens /files/ is sent to sign in."""
    page.goto("/files/")

    expect(page).to_have_url(re.compile(r"/login/\?next=/files/$"))


def test_35_regular_user_cannot_change_roles_by_direct_request(
    user_page: Page, admin_browser: Page
):
    """TC-35: the server refuses a role change sent by a regular user.

    TC-10 shows the links are hidden. This test checks the server itself:
    demo_user sends the roles form straight to the server and tries to give
    themselves the admin role.
    """
    users_page = UsersPage(admin_browser).open()
    user_id = users_page.user_id(config.REGULAR_USER.username)
    users_page.open_roles_of(config.REGULAR_USER.username)
    admin_role_id = UserRolesPage(admin_browser).role_id("admin")

    response = send_form(
        user_page, f"/manage/users/{user_id}/roles/", {"groups": admin_role_id}
    )

    assert response.status == 403
    assert ACCESS_DENIED in response.text()
    users_page.open()
    users_page.search(config.REGULAR_USER.username)
    admin_badge = users_page.role_badge(config.REGULAR_USER.username, "admin")
    expect(admin_badge).to_have_count(0)


def test_36_regular_user_cannot_deactivate_user_by_direct_request(
    user_page: Page, admin_browser: Page, new_user
):
    """TC-36: the server refuses to switch a user off when a regular user asks."""
    users_page = UsersPage(admin_browser).open()
    user_id = users_page.user_id(new_user.username)

    response = send_form(user_page, f"/manage/users/{user_id}/toggle-active/", {})

    assert response.status == 403
    assert ACCESS_DENIED in response.text()
    users_page.open()
    users_page.search(new_user.username)
    expect(users_page.deactivate_button(new_user.username)).to_be_visible()
