"""Keep the Keycloak password the same as the Django one.

A password can change past the panel: in /admin/, with `manage.py
changepassword`, seed_demo_users or a shell. All of them save the user,
so the check is made on saving.
"""

import logging

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from accounts.keycloak_admin import KeycloakUnavailable, push_password

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=settings.AUTH_USER_MODEL)
def note_password_change(sender, instance, update_fields=None, **kwargs):
    instance._keycloak_password_changed = False
    # A new user gets the password with the account itself (push_user).
    if not settings.OIDC_ENABLED or instance.pk is None:
        return
    # Signing in saves only last_login: no need to ask the database then.
    if update_fields is not None and "password" not in update_fields:
        return
    old = (
        sender.objects.filter(pk=instance.pk).values_list("password", flat=True).first()
    )
    instance._keycloak_password_changed = old is not None and old != instance.password


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def send_password_to_keycloak(sender, instance, **kwargs):
    if not getattr(instance, "_keycloak_password_changed", False):
        return
    instance._keycloak_password_changed = False
    # Only once the new password is really saved.
    transaction.on_commit(lambda: send_password(instance))


def send_password(user):
    # Keycloak being down must not undo a password change already made.
    try:
        push_password(user)
    except KeycloakUnavailable as error:
        logger.error(
            "The new password of %s did not reach Keycloak: %s", user.username, error
        )
