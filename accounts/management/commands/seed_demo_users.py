"""Demo users for local checks."""

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.permissions import ADMIN_GROUP_NAME, USER_GROUP_NAME

# The prefix is how the command recognises its own accounts, --delete included.
DEMO_PREFIX = "demo_"

DEFAULT_PASSWORD = "demo-password-123"

# username, first name, last name, roles, is_staff, is_active, note
DEMO_USERS = [
    (
        "demo_admin",
        "Alice",
        "Adminson",
        [ADMIN_GROUP_NAME],
        False,
        True,
        "admin through the admin group",
    ),
    (
        "demo_staff",
        "Sam",
        "Staffman",
        [],
        True,
        True,
        "admin through the is_staff flag",
    ),
    (
        "demo_user",
        "John",
        "Smith",
        [USER_GROUP_NAME],
        False,
        True,
        "regular user, gets 403 on /manage/",
    ),
    (
        "demo_inactive",
        "Peter",
        "Inactive",
        [USER_GROUP_NAME],
        False,
        False,
        "deactivated, cannot sign in",
    ),
]

EXTRA_NAMES = [
    ("Maria", "Johnson"),
    ("Oliver", "Brown"),
    ("Diana", "Wilson"),
    ("Nathan", "Taylor"),
    ("Emily", "Davies"),
    ("Adam", "Evans"),
    ("Olivia", "Thomas"),
    ("Patrick", "Roberts"),
    ("Karen", "Walker"),
    ("Robert", "Hughes"),
]


class Command(BaseCommand):
    help = (
        "Create demo users (demo_*) for local checks: an admin by group, an "
        "admin by is_staff, a regular user, a deactivated one, and a batch of "
        "regular users so that pagination has something to paginate."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help=f"password for every demo account (default: {DEFAULT_PASSWORD})",
        )
        parser.add_argument(
            "--extra",
            type=int,
            default=10,
            help="how many extra regular users to create (default: 10)",
        )
        parser.add_argument(
            "--delete",
            action="store_true",
            help=f"delete every user with the {DEMO_PREFIX} prefix and exit",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="allow running with DEBUG=False (refused by default)",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "DEBUG=False: this command creates accounts with a well-known "
                "password and refuses to run outside development. If you really "
                "mean it, pass --force."
            )

        if options["delete"]:
            deleted, _ = User.objects.filter(username__startswith=DEMO_PREFIX).delete()
            self.stdout.write(
                self.style.SUCCESS(f"Demo users deleted (objects removed: {deleted}).")
            )
            return

        extra = max(0, min(options["extra"], len(EXTRA_NAMES)))
        if options["extra"] > len(EXTRA_NAMES):
            self.stderr.write(
                self.style.WARNING(
                    f"Asked for {options['extra']} extra users, but the name "
                    f"list holds {len(EXTRA_NAMES)} - creating {extra}."
                )
            )
        password = options["password"]

        with transaction.atomic():
            groups = {
                name: Group.objects.get_or_create(name=name)[0]
                for name in (ADMIN_GROUP_NAME, USER_GROUP_NAME)
            }
            rows = [self.upsert(spec, password, groups) for spec in DEMO_USERS]
            for index in range(extra):
                first_name, last_name = EXTRA_NAMES[index]
                spec = (
                    f"{DEMO_PREFIX}user{index + 1:02d}",
                    first_name,
                    last_name,
                    [USER_GROUP_NAME],
                    False,
                    True,
                    "regular user (for search and pagination)",
                )
                rows.append(self.upsert(spec, password, groups))

        self.report(rows, password)

    def upsert(self, spec, password, groups):
        """Create or update a user and return one row for the report."""
        username, first_name, last_name, role_names, is_staff, is_active, note = spec

        user, created = User.objects.get_or_create(username=username)
        user.first_name = first_name
        user.last_name = last_name
        user.email = f"{username}@example.com"
        user.is_staff = is_staff
        user.is_active = is_active
        user.set_password(password)
        user.save()
        user.groups.set([groups[name] for name in role_names])

        return (username, ", ".join(role_names) or "-", note, created)

    def report(self, rows, password):
        created_count = sum(1 for *_, created in rows if created)
        width = max(len(username) for username, *_ in rows)

        self.stdout.write("")
        self.stdout.write(f"{'USERNAME'.ljust(width)}  ROLES        PURPOSE")
        for username, roles, note, created in rows:
            mark = "+" if created else "="
            self.stdout.write(
                f"{mark} {username.ljust(width)}  {roles.ljust(11)}  {note}"
            )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Password for all of them: {password}"))
        updated_count = len(rows) - created_count
        self.stdout.write(
            self.style.SUCCESS(f"Created: {created_count}, updated: {updated_count}.")
        )
        self.stdout.write("Remove them all: manage.py seed_demo_users --delete")
