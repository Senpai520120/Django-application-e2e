from django.conf import settings
from django.db import models


class KeycloakIdentity(models.Model):
    """Which Keycloak account is this Django user.

    Keycloak's "sub" never changes, unlike the username, so after the first
    sign-in a user is found by it: a Keycloak account renamed to somebody
    else's username does not become that somebody.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="keycloak_identity",
    )
    sub = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return f"{self.user} = {self.sub}"
