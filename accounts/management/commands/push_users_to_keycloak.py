"""Give every Django user without a Keycloak account one, password included.

For the switch to SSO: users created while it was off keep signing in with
their own password, now on the Keycloak form. Safe to re-run: users already
linked are left alone, and a username Keycloak already has is skipped
(an ordinary user is linked to it on the first sign-in; an admin needs
`link_keycloak_user`).

    python manage.py push_users_to_keycloak
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from accounts.keycloak_admin import KeycloakUnavailable, KeycloakUserExists, push_user


class Command(BaseCommand):
    help = "Create Keycloak accounts for Django users that have none."

    def handle(self, *args, **options):
        if not settings.OIDC_ENABLED:
            raise CommandError("OIDC_ENABLED is off: there is no Keycloak to push to")

        created = skipped = 0
        for user in User.objects.filter(keycloak_identity__isnull=True).order_by("pk"):
            try:
                push_user(user)
            except KeycloakUserExists:
                skipped += 1
                self.stdout.write(f"already in Keycloak: {user.username}")
                continue
            except KeycloakUnavailable as error:
                raise CommandError(f"Keycloak is not available: {error}") from error
            created += 1
            self.stdout.write(f"created in Keycloak: {user.username}")

        self.stdout.write(
            self.style.SUCCESS(f"Done. Created: {created}, already there: {skipped}.")
        )
