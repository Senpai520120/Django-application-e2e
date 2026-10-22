"""Link Django users to Keycloak accounts by hand.

Sign-in links a user by username only when the user has no admin rights.
Admins, staff and superusers are linked here, with the Keycloak account id
(the "ID" on the user's page in the Keycloak admin console):

    python manage.py link_keycloak_user olga=2b0f5c1e-... root=91d4...

--replace moves a link that already exists, for example to a Keycloak account
that was deleted and created again (it gets a new id).
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import KeycloakIdentity


class Command(BaseCommand):
    help = "Link Django users to Keycloak accounts: username=keycloak-id ..."

    def add_arguments(self, parser):
        parser.add_argument("links", nargs="+", metavar="username=keycloak-id")
        parser.add_argument(
            "--replace",
            action="store_true",
            help="move links that already point elsewhere",
        )

    @transaction.atomic
    def handle(self, *args, links, replace, **options):
        for link in links:
            username, sep, sub = link.partition("=")
            if not sep or not username or not sub:
                raise CommandError(f"expected username=keycloak-id, got {link!r}")
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                raise CommandError(f"no user {username!r}") from None

            taken = KeycloakIdentity.objects.filter(sub=sub).exclude(user=user)
            current = KeycloakIdentity.objects.filter(user=user).exclude(sub=sub)
            if (taken.exists() or current.exists()) and not replace:
                raise CommandError(
                    f"{username} or {sub} is already linked elsewhere; "
                    "--replace moves the link"
                )
            taken.delete()
            current.delete()
            KeycloakIdentity.objects.get_or_create(user=user, sub=sub)
            self.stdout.write(f"{username} = {sub}")
