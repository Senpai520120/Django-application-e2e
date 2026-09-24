"""Role seeding: the data migration and the management command."""

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command

from accounts.permissions import DEFAULT_GROUP_NAMES


@pytest.mark.django_db
def test_migration_creates_default_groups():
    """Roles exist right after `migrate`; nothing else has to be run."""
    assert set(Group.objects.values_list("name", flat=True)) == set(DEFAULT_GROUP_NAMES)


@pytest.mark.django_db
def test_seed_groups_command_is_idempotent():
    call_command("seed_groups")
    call_command("seed_groups")

    assert Group.objects.filter(name__in=DEFAULT_GROUP_NAMES).count() == len(
        DEFAULT_GROUP_NAMES
    )


@pytest.mark.django_db
def test_seed_groups_command_restores_deleted_group():
    Group.objects.filter(name="admin").delete()

    call_command("seed_groups")

    assert Group.objects.filter(name="admin").exists()
