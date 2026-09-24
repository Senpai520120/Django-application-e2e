"""Fixtures shared by the test suite."""

import pytest
from django.contrib.auth.models import Group, User

from accounts.permissions import ADMIN_GROUP_NAME, USER_GROUP_NAME

PASSWORD = "Str0ng-Pass!2024"


@pytest.fixture
def password():
    return PASSWORD


@pytest.fixture
def admin_group(db):
    """The admin group is created by the accounts.0001_seed_groups migration."""
    return Group.objects.get(name=ADMIN_GROUP_NAME)


@pytest.fixture
def user_group(db):
    return Group.objects.get(name=USER_GROUP_NAME)


@pytest.fixture
def plain_user(db, user_group):
    """A regular user: holds the user role, has no access to the panel."""
    user = User.objects.create_user(
        username="ivan",
        password=PASSWORD,
        email="ivan@example.com",
        first_name="John",
        last_name="Smith",
    )
    user.groups.add(user_group)
    return user


@pytest.fixture
def group_admin(db, admin_group):
    """Admin through the admin group, with neither is_staff nor superuser."""
    user = User.objects.create_user(
        username="boss",
        password=PASSWORD,
        email="boss@example.com",
    )
    user.groups.add(admin_group)
    return user


@pytest.fixture
def staff_admin(db):
    """Admin through the is_staff flag."""
    return User.objects.create_user(
        username="stafferson",
        password=PASSWORD,
        is_staff=True,
    )


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser(
        username="root",
        email="root@example.com",
        password=PASSWORD,
    )
