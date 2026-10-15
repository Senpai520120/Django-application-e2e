"""Admin panel: granting and revoking roles, the audit log, the roles page."""

import pytest
from playwright.sync_api import Page, expect

import config
from pages.audit_page import AuditPage
from pages.roles_page import RolesPage
from pages.user_roles_page import UserRolesPage
from pages.users_page import UsersPage


def test_17_admin_grants_admin_role(admin_page: Page, new_user):
    """TC-17: an admin grants the admin role and it shows in the user list."""
    users_page = UsersPage(admin_page).open()
    users_page.open_roles_of(new_user.username)
    roles_form = UserRolesPage(admin_page)

    roles_form.role_checkbox("admin").check()
    roles_form.save()

    expect(users_page.status_message).to_contain_text(
        f"Roles of {new_user.username} updated"
    )
    users_page.search(new_user.username)
    expect(users_page.role_badge(new_user.username, "admin")).to_be_visible()


def test_18_admin_revokes_role(admin_page: Page, new_user):
    """TC-18: an admin takes a role away and it disappears from the user list."""
    users_page = UsersPage(admin_page).open()
    users_page.open_roles_of(new_user.username)
    roles_form = UserRolesPage(admin_page)
    roles_form.role_checkbox("user").check()
    roles_form.save()

    users_page.open_roles_of(new_user.username)
    roles_form.role_checkbox("user").uncheck()
    roles_form.save()

    users_page.search(new_user.username)
    expect(users_page.role_badge(new_user.username, "user")).to_have_count(0)


def test_19_cancel_on_roles_form_changes_nothing(admin_page: Page, new_user):
    """TC-19: leaving the roles form with "Cancel" keeps the roles as they were."""
    users_page = UsersPage(admin_page).open()
    users_page.open_roles_of(new_user.username)
    roles_form = UserRolesPage(admin_page)

    roles_form.role_checkbox("admin").check()
    roles_form.cancel_link.click()

    users_page.search(new_user.username)
    expect(users_page.role_badge(new_user.username, "admin")).to_have_count(0)


def test_20_admin_cannot_remove_own_admin_role(admin_page: Page):
    """TC-20: an admin cannot take the admin role from themselves."""
    users_page = UsersPage(admin_page).open()
    users_page.open_roles_of(config.ADMIN.username)
    roles_form = UserRolesPage(admin_page)

    roles_form.role_checkbox("admin").uncheck()
    roles_form.save()

    expect(
        roles_form.error_message("You cannot take the admin role from yourself")
    ).to_be_visible()
    users_page.open()
    users_page.search(config.ADMIN.username)
    expect(users_page.role_badge(config.ADMIN.username, "admin")).to_be_visible()


def test_21_role_change_is_written_to_audit_log(admin_page: Page, new_user):
    """TC-21: granting a role adds a record to the audit log: who, what, to whom."""
    users_page = UsersPage(admin_page).open()
    users_page.open_roles_of(new_user.username)
    roles_form = UserRolesPage(admin_page)
    roles_form.role_checkbox("user").check()
    roles_form.save()

    audit_page = AuditPage(admin_page).open()

    expect(audit_page.newest_record_cell(config.ADMIN.username)).to_be_visible()
    expect(audit_page.newest_record_cell("granted")).to_be_visible()
    expect(audit_page.newest_record_cell("user")).to_be_visible()
    expect(audit_page.newest_record_cell(new_user.username)).to_be_visible()


def test_22_roles_page_counts_new_member(admin_page: Page, new_user):
    """TC-22: granting the admin role adds 1 to its counter on the Roles page."""
    roles_page = RolesPage(admin_page).open()
    admins_before = roles_page.members_count("admin")

    users_page = UsersPage(admin_page).open()
    users_page.open_roles_of(new_user.username)
    roles_form = UserRolesPage(admin_page)
    roles_form.role_checkbox("admin").check()
    roles_form.save()

    roles_page.open()
    expect(roles_page.members_count_cell("admin")).to_have_text(str(admins_before + 1))


def test_39_role_revoke_is_written_to_audit_log(admin_page: Page, new_user):
    """TC-39: taking a role away adds a "revoked" record to the audit log."""
    users_page = UsersPage(admin_page).open()
    users_page.open_roles_of(new_user.username)
    roles_form = UserRolesPage(admin_page)
    roles_form.role_checkbox("user").check()
    roles_form.save()

    users_page.open_roles_of(new_user.username)
    roles_form.role_checkbox("user").uncheck()
    roles_form.save()

    audit_page = AuditPage(admin_page).open()
    expect(audit_page.newest_record_cell(config.ADMIN.username)).to_be_visible()
    expect(audit_page.newest_record_cell("revoked")).to_be_visible()
    expect(audit_page.newest_record_cell("user")).to_be_visible()
    expect(audit_page.newest_record_cell(new_user.username)).to_be_visible()


# xfail = "expected to fail". The app does not log this yet (bug #142).
# strict=True: when the bug is fixed, the test passes and pytest reports it,
# so we know to remove this marker.
@pytest.mark.xfail(
    reason="Bug #142: the audit log does not record deactivation", strict=True
)
def test_40_user_deactivation_is_written_to_audit_log(admin_page: Page, new_user):
    """TC-40: switching a user off adds a record about that user to the audit log."""
    users_page = UsersPage(admin_page).open()
    users_page.search(new_user.username)

    users_page.deactivate(new_user.username)

    audit_page = AuditPage(admin_page).open()
    expect(audit_page.newest_record_cell(new_user.username)).to_be_visible()
