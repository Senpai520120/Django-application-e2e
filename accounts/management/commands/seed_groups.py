from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from accounts.permissions import DEFAULT_GROUP_NAMES


class Command(BaseCommand):
    help = "Create the baseline role groups (admin, user). Safe to re-run."

    def handle(self, *args, **options):
        created_names = []
        for name in DEFAULT_GROUP_NAMES:
            _, created = Group.objects.get_or_create(name=name)
            if created:
                created_names.append(name)
                self.stdout.write(self.style.SUCCESS(f"Role created: {name}"))
            else:
                self.stdout.write(f"Role already exists: {name}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Roles created: {len(created_names)}, "
                f"baseline roles in total: {len(DEFAULT_GROUP_NAMES)}."
            )
        )
