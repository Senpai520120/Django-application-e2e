"""Access control for the /manage/ panel."""

import pytest
from django.urls import reverse


def panel_urls(user_pk):
    return [
        reverse("panel:user_list"),
        reverse("panel:role_list"),
        reverse("panel:audit_log"),
        reverse("panel:user_create"),
        reverse("panel:user_roles", args=[user_pk]),
    ]


@pytest.mark.django_db
def test_manage_root_url_is_panel():
    assert reverse("panel:user_list") == "/manage/"


@pytest.mark.django_db
def test_anonymous_is_redirected_to_login(client, plain_user):
    for url in panel_urls(plain_user.pk):
        response = client.get(url)

        assert response.status_code == 302, url
        assert response.url == f"{reverse('login')}?next={url}"


@pytest.mark.django_db
def test_plain_user_gets_403(client, plain_user):
    client.force_login(plain_user)

    for url in panel_urls(plain_user.pk):
        response = client.get(url)

        assert response.status_code == 403, url


@pytest.mark.django_db
def test_user_from_admin_group_gets_200(client, group_admin, plain_user):
    client.force_login(group_admin)

    for url in panel_urls(plain_user.pk):
        response = client.get(url)

        assert response.status_code == 200, url


@pytest.mark.django_db
def test_staff_user_gets_200(client, staff_admin, plain_user):
    client.force_login(staff_admin)

    assert client.get(reverse("panel:user_list")).status_code == 200
    assert (
        client.get(reverse("panel:user_roles", args=[plain_user.pk])).status_code == 200
    )


@pytest.mark.django_db
def test_superuser_gets_200(client, superuser):
    client.force_login(superuser)

    assert client.get(reverse("panel:user_list")).status_code == 200


@pytest.mark.django_db
def test_losing_admin_group_closes_the_panel(client, group_admin, admin_group):
    """Permissions are checked on every request, not once at login."""
    client.force_login(group_admin)
    assert client.get(reverse("panel:user_list")).status_code == 200

    group_admin.groups.remove(admin_group)

    assert client.get(reverse("panel:user_list")).status_code == 403


@pytest.mark.django_db
def test_admin_sees_panel_link_on_home(client, group_admin):
    client.force_login(group_admin)

    response = client.get(reverse("home"))

    assert reverse("panel:user_list") in response.content.decode()


@pytest.mark.django_db
def test_permission_check_costs_one_query(client, group_admin):
    """Both the mixin and the context processor ask, but one query must suffice."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    client.force_login(group_admin)

    with CaptureQueriesContext(connection) as queries:
        client.get(reverse("panel:user_list"))

    group_checks = [
        query["sql"]
        for query in queries.captured_queries
        if 'SELECT 1 AS "a"' in query["sql"] and "auth_user_groups" in query["sql"]
    ]
    assert len(group_checks) == 1
