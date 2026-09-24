"""Granting and revoking roles through the panel."""

from urllib.parse import quote

import pytest
from django.test import Client
from django.urls import reverse

from panel.models import RoleChange


@pytest.mark.django_db
def test_admin_assigns_role_and_db_changes(
    client, group_admin, plain_user, admin_group, user_group
):
    client.force_login(group_admin)
    url = reverse("panel:user_roles", args=[plain_user.pk])

    response = client.post(url, {"groups": [user_group.pk, admin_group.pk]})

    assert response.status_code == 302
    assert response.url == reverse("panel:user_list")
    plain_user.refresh_from_db()
    assert set(plain_user.groups.values_list("name", flat=True)) == {"user", "admin"}


@pytest.mark.django_db
def test_admin_removes_role_and_db_changes(client, group_admin, plain_user, user_group):
    client.force_login(group_admin)
    assert plain_user.groups.filter(pk=user_group.pk).exists()

    client.post(reverse("panel:user_roles", args=[plain_user.pk]), {"groups": []})

    assert plain_user.groups.count() == 0


@pytest.mark.django_db
def test_role_change_is_written_to_audit_log(
    client, group_admin, plain_user, admin_group
):
    client.force_login(group_admin)

    client.post(
        reverse("panel:user_roles", args=[plain_user.pk]),
        {"groups": [admin_group.pk]},
    )

    changes = RoleChange.objects.filter(target=plain_user).order_by("group_name")
    assert changes.count() == 2
    assert (changes[0].group_name, changes[0].action) == (
        "admin",
        RoleChange.ACTION_ADDED,
    )
    assert (changes[1].group_name, changes[1].action) == (
        "user",
        RoleChange.ACTION_REMOVED,
    )
    assert {change.actor for change in changes} == {group_admin}


@pytest.mark.django_db
def test_saving_without_changes_writes_no_audit_entries(
    client, group_admin, plain_user, user_group
):
    client.force_login(group_admin)

    client.post(
        reverse("panel:user_roles", args=[plain_user.pk]),
        {"groups": [user_group.pk]},
    )

    assert RoleChange.objects.count() == 0
    assert plain_user.groups.count() == 1


@pytest.mark.django_db
def test_plain_user_cannot_change_roles(client, plain_user, admin_group):
    client.force_login(plain_user)

    response = client.post(
        reverse("panel:user_roles", args=[plain_user.pk]),
        {"groups": [admin_group.pk]},
    )

    assert response.status_code == 403
    assert not plain_user.groups.filter(name="admin").exists()
    assert RoleChange.objects.count() == 0


@pytest.mark.django_db
def test_post_without_csrf_token_is_rejected(group_admin, plain_user, admin_group):
    """CSRF protection is on and is not disabled anywhere in the project."""
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(group_admin)

    response = csrf_client.post(
        reverse("panel:user_roles", args=[plain_user.pk]),
        {"groups": [admin_group.pk]},
    )

    assert response.status_code == 403
    assert not plain_user.groups.filter(name="admin").exists()


@pytest.mark.django_db
def test_admin_cannot_take_admin_role_from_himself(client, group_admin, admin_group):
    """Otherwise the last admin locks themselves out and only a shell helps."""
    client.force_login(group_admin)

    response = client.post(
        reverse("panel:user_roles", args=[group_admin.pk]), {"groups": []}
    )

    assert response.status_code == 200
    assert "groups" in response.context["form"].errors
    assert group_admin.groups.filter(name="admin").exists()
    assert client.get(reverse("panel:user_list")).status_code == 200


@pytest.mark.django_db
def test_superuser_may_drop_own_group(client, superuser, admin_group):
    """The ban is narrow: a superuser keeps access after dropping the group."""
    superuser.groups.add(admin_group)
    client.force_login(superuser)

    response = client.post(
        reverse("panel:user_roles", args=[superuser.pk]), {"groups": []}
    )

    assert response.status_code == 302
    assert superuser.groups.count() == 0
    assert client.get(reverse("panel:user_list")).status_code == 200


@pytest.mark.django_db
def test_audit_survives_deletion_of_the_user(
    client, group_admin, plain_user, admin_group
):
    client.force_login(group_admin)
    client.post(
        reverse("panel:user_roles", args=[plain_user.pk]), {"groups": [admin_group.pk]}
    )
    username = plain_user.username

    plain_user.delete()

    changes = RoleChange.objects.all()
    assert changes.count() == 2
    assert {change.target_username for change in changes} == {username}
    assert changes.first().target is None


@pytest.mark.django_db
def test_after_saving_roles_admin_returns_to_the_same_list_page(
    client, group_admin, plain_user, admin_group
):
    client.force_login(group_admin)
    back = f"{reverse('panel:user_list')}?q=ivan&page=1"
    # The template puts the address into ?next= through the urlencode filter.
    next_param = quote(back, safe="/")

    response = client.post(
        f"{reverse('panel:user_roles', args=[plain_user.pk])}?next={next_param}",
        {"groups": [admin_group.pk]},
    )

    assert response.url == back


@pytest.mark.django_db
def test_open_redirect_through_next_is_ignored(client, group_admin, plain_user):
    client.force_login(group_admin)

    response = client.post(
        f"{reverse('panel:user_roles', args=[plain_user.pk])}?next=https://evil.example",
        {"groups": []},
    )

    assert response.url == reverse("panel:user_list")
