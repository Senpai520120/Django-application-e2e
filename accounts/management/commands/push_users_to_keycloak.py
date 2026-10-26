"""Give every Django user without a Keycloak account one, password included.

For the switch to SSO: users created while it was off keep signing in with
their own password, now on the Keycloak form. A link whose Keycloak account
is gone is only reported, unless KEYCLOAK_REMAKE_LOST_ACCOUNTS is on (the
development Keycloak, which forgets its accounts on `down`): then the
account is made again. In production a missing account was deleted on
purpose, and making it again would undo that.

Safe to re-run: accounts that exist are left alone, and a username Keycloak
already has is skipped (an ordinary user is linked to it on the first
sign-in; an admin needs `link_keycloak_user`).

    python manage.py push_users_to_keycloak
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from accounts.keycloak_admin import (
    KeycloakRefused,
    KeycloakUnavailable,
    KeycloakUserExists,
    account_exists,
    push_user,
)
from accounts.models import KeycloakIdentity


class Command(BaseCommand):
    help = "Create Keycloak accounts for Django users that have none."

    def handle(self, *args, **options):
        if not settings.OIDC_ENABLED:
            raise CommandError("OIDC_ENABLED is off: there is no Keycloak to push to")

        created = skipped = 0
        users = User.objects.select_related("keycloak_identity").order_by("pk")
        try:
            for user in users:
                identity = getattr(user, "keycloak_identity", None)
                if identity is not None:
                    if account_exists(identity.sub):
                        continue
                    if not settings.KEYCLOAK_REMAKE_LOST_ACCOUNTS:
                        skipped += 1
                        self.stdout.write(
                            f"gone from Keycloak, left so: {user.username}"
                        )
                        continue
                    # The account behind the link is gone: the link is of no use.
                    KeycloakIdentity.objects.filter(pk=identity.pk).delete()
                    user.keycloak_identity = None
                    self.stdout.write(f"gone from Keycloak: {user.username}")
                try:
                    push_user(user)
                except (KeycloakUserExists, KeycloakRefused) as refusal:
                    skipped += 1
                    self.stdout.write(
                        f"not created in Keycloak: {user.username} ({refusal})"
                    )
                    continue
                created += 1
                self.stdout.write(f"created in Keycloak: {user.username}")
        except KeycloakUnavailable as error:
            raise CommandError(f"Keycloak is not available: {error}") from error

        self.stdout.write(
            self.style.SUCCESS(f"Done. Created: {created}, not created: {skipped}.")
        )
