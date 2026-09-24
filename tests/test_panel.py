"""User list, search, pagination and the rest of the panel."""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from panel.models import RoleChange


@pytest.mark.django_db
def test_user_list_shows_users_with_roles(client, group_admin, plain_user):
    client.force_login(group_admin)

    response = client.get(reverse("panel:user_list"))
    content = response.content.decode()

    assert list(response.context["users"]) == [group_admin, plain_user]
    assert plain_user.email in content
    # The role badge specifically, not the word "user" that markup always has.
    assert '<span class="badge">user</span>' in content


@pytest.mark.django_db
def test_role_list_shows_groups_with_member_count(client, group_admin, plain_user):
    client.force_login(group_admin)

    response = client.get(reverse("panel:role_list"))

    roles = {role.name: role.members_count for role in response.context["roles"]}
    assert roles == {"admin": 1, "user": 1}


@pytest.mark.django_db
def test_search_filters_users(client, group_admin, plain_user):
    client.force_login(group_admin)

    response = client.get(reverse("panel:user_list"), {"q": "ivan@example"})

    usernames = [user.username for user in response.context["users"]]
    assert usernames == [plain_user.username]


@pytest.mark.django_db
def test_user_list_is_paginated(client, group_admin):
    User.objects.bulk_create(User(username=f"user{index:02d}") for index in range(15))
    client.force_login(group_admin)

    first_page = client.get(reverse("panel:user_list"))
    second_page = client.get(reverse("panel:user_list"), {"page": 2})

    assert first_page.context["is_paginated"] is True
    assert len(first_page.context["users"]) == 10
    assert len(second_page.context["users"]) == 6  # 15 created plus the admin


@pytest.mark.django_db
def test_admin_can_deactivate_and_activate_user(client, group_admin, plain_user):
    client.force_login(group_admin)
    url = reverse("panel:user_toggle_active", args=[plain_user.pk])

    client.post(url)
    plain_user.refresh_from_db()
    assert plain_user.is_active is False

    client.post(url)
    plain_user.refresh_from_db()
    assert plain_user.is_active is True


@pytest.mark.django_db
def test_admin_cannot_deactivate_self(client, group_admin):
    client.force_login(group_admin)

    client.post(reverse("panel:user_toggle_active", args=[group_admin.pk]))

    group_admin.refresh_from_db()
    assert group_admin.is_active is True


@pytest.mark.django_db
def test_toggle_active_requires_post(client, group_admin, plain_user):
    client.force_login(group_admin)

    response = client.get(reverse("panel:user_toggle_active", args=[plain_user.pk]))

    assert response.status_code == 405


@pytest.mark.django_db
def test_admin_creates_user_with_role(client, group_admin, user_group, password):
    client.force_login(group_admin)

    response = client.post(
        reverse("panel:user_create"),
        {
            "username": "newbie",
            "email": "newbie@example.com",
            "first_name": "Peter",
            "last_name": "Parker",
            "password1": password,
            "password2": password,
            "groups": [user_group.pk],
        },
    )

    assert response.status_code == 302
    created = User.objects.get(username="newbie")
    assert created.check_password(password)
    assert created.password != password
    assert list(created.groups.values_list("name", flat=True)) == ["user"]
    assert RoleChange.objects.filter(
        target=created, action=RoleChange.ACTION_ADDED, group_name="user"
    ).exists()


@pytest.mark.django_db
def test_audit_log_page_lists_changes(client, group_admin, plain_user, admin_group):
    client.force_login(group_admin)
    client.post(
        reverse("panel:user_roles", args=[plain_user.pk]),
        {"groups": [admin_group.pk]},
    )

    response = client.get(reverse("panel:audit_log"))
    content = response.content.decode()

    assert response.status_code == 200
    assert group_admin.username in content
    assert plain_user.username in content


@pytest.mark.django_db
def test_user_list_has_no_n_plus_one(client, group_admin, django_assert_num_queries):
    """The query count must not grow along with the number of users."""
    client.force_login(group_admin)
    url = reverse("panel:user_list")

    with django_assert_num_queries(6):
        client.get(url)

    User.objects.bulk_create(User(username=f"bulk{i:02d}") for i in range(9))

    with django_assert_num_queries(6):
        client.get(url)
