"""The demo users command."""

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.management.commands.seed_demo_users import DEFAULT_PASSWORD, DEMO_PREFIX


@pytest.fixture
def debug_mode(settings):
    """The command runs in development only."""
    settings.DEBUG = True
    return settings


@pytest.mark.django_db
def test_creates_users_with_expected_roles_and_flags(debug_mode):
    call_command("seed_demo_users", extra=0)

    admin = User.objects.get(username="demo_admin")
    staff = User.objects.get(username="demo_staff")
    plain = User.objects.get(username="demo_user")
    inactive = User.objects.get(username="demo_inactive")

    assert list(admin.groups.values_list("name", flat=True)) == ["admin"]
    assert admin.is_staff is False and admin.is_superuser is False
    assert staff.is_staff is True and staff.groups.count() == 0
    assert list(plain.groups.values_list("name", flat=True)) == ["user"]
    assert inactive.is_active is False


@pytest.mark.django_db
def test_password_is_usable_and_hashed(debug_mode):
    call_command("seed_demo_users", extra=0)

    user = User.objects.get(username="demo_admin")

    assert user.check_password(DEFAULT_PASSWORD)
    assert DEFAULT_PASSWORD not in user.password


@pytest.mark.django_db
def test_custom_password_and_extra_users(debug_mode):
    call_command("seed_demo_users", extra=3, password="My-Own-Pass-42")

    demo_users = User.objects.filter(username__startswith=DEMO_PREFIX)

    assert demo_users.count() == 7  # 4 baseline plus 3 extra
    assert User.objects.get(username="demo_user03").check_password("My-Own-Pass-42")


@pytest.mark.django_db
def test_is_idempotent_and_restores_state(debug_mode):
    call_command("seed_demo_users", extra=0)
    admin = User.objects.get(username="demo_admin")
    admin.groups.clear()
    admin.is_active = False
    admin.save()

    call_command("seed_demo_users", extra=0)

    admin.refresh_from_db()
    assert User.objects.filter(username__startswith=DEMO_PREFIX).count() == 4
    assert list(admin.groups.values_list("name", flat=True)) == ["admin"]
    assert admin.is_active is True


@pytest.mark.django_db
def test_delete_removes_only_demo_users(debug_mode):
    User.objects.create_user("real_user", password="Str0ng-Pass!2024")
    call_command("seed_demo_users", extra=2)

    call_command("seed_demo_users", delete=True)

    assert User.objects.filter(username__startswith=DEMO_PREFIX).count() == 0
    assert User.objects.filter(username="real_user").exists()


@pytest.mark.django_db
def test_refuses_to_run_with_debug_false(settings):
    settings.DEBUG = False

    with pytest.raises(CommandError, match="DEBUG=False"):
        call_command("seed_demo_users")

    assert User.objects.count() == 0


@pytest.mark.django_db
def test_force_allows_run_with_debug_false(settings):
    settings.DEBUG = False

    call_command("seed_demo_users", extra=0, force=True)

    assert User.objects.filter(username__startswith=DEMO_PREFIX).count() == 4
