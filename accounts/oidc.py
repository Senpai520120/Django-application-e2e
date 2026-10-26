"""Sign-in through Keycloak: who the user is.

Keycloak answers only "who you are". What the user may do stays in the panel:
roles are Django groups, and a user switched off in the panel cannot sign in
even with a valid Keycloak password (the callback view checks is_active).

A refusal here raises PermissionDenied: Django's authenticate() turns it into
"nobody", and the user lands on the sign-in failed page instead of an error.
"""

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from accounts.models import KeycloakIdentity
from accounts.permissions import ADMIN_GROUP_NAME, USER_GROUP_NAME

logger = logging.getLogger(__name__)


class KeycloakBackend(OIDCAuthenticationBackend):
    """Finds the Django user by the Keycloak account id ("sub")."""

    def get_userinfo(self, access_token, id_token, payload):
        claims = super().get_userinfo(access_token, id_token, payload)
        # The link is kept by sub, so it must be the sub of the signed id
        # token, not only whatever the userinfo answer says (OIDC Core 5.3.2).
        if claims.get("sub") != payload.get("sub"):
            logger.warning("Keycloak sign-in refused: userinfo sub != id token sub")
            raise PermissionDenied
        return claims

    def verify_claims(self, claims):
        # Only the id and the username are needed; email is optional.
        username = claims.get("preferred_username") or ""
        max_length = self.UserModel._meta.get_field("username").max_length
        if not claims.get("sub") or not username or len(username) > max_length:
            logger.warning("Keycloak sign-in refused: no sub or no usable username")
            raise PermissionDenied
        return True

    def filter_users_by_claims(self, claims):
        linked = self.UserModel.objects.filter(keycloak_identity__sub=claims["sub"])
        if linked.exists():
            return linked
        # First sign-in of somebody the app already knows (demo_user and the
        # rest): the same username. Keycloak lowercases it, so case is ignored,
        # unless the very same spelling exists. Never an account already linked
        # to another Keycloak account, and never one with admin rights in the
        # panel or /admin/: those are linked with `manage.py link_keycloak_user`.
        candidates = self.UserModel.objects.filter(
            keycloak_identity__isnull=True,
            is_staff=False,
            is_superuser=False,
        ).exclude(groups__name=ADMIN_GROUP_NAME)
        username = claims["preferred_username"]
        exact = candidates.filter(username=username)
        if exact.exists():
            return exact
        found = candidates.filter(username__iexact=username)
        if found.count() > 1:
            # "IVAN" and "Ivan" for Keycloak's "ivan": which one is a guess.
            logger.warning("Keycloak sign-in refused: %s is ambiguous", username)
            raise PermissionDenied
        return found

    def create_user(self, claims):
        username = claims["preferred_username"]
        if self.UserModel.objects.filter(username__iexact=username).exists():
            # Taken by an account filter_users_by_claims may not link.
            logger.warning("Keycloak sign-in refused: username %s is taken", username)
            raise PermissionDenied
        try:
            with transaction.atomic():
                # No password: this user can come in only through Keycloak.
                user = self.UserModel.objects.create_user(username)
                group, _ = Group.objects.get_or_create(name=USER_GROUP_NAME)
                user.groups.add(group)
                return self.update_user(user, claims)
        except IntegrityError:
            # The same first sign-in finished at once in another tab.
            logger.warning("Keycloak sign-in refused: %s was just created", username)
            raise PermissionDenied from None

    def update_user(self, user, claims):
        try:
            with transaction.atomic():
                identity, _ = KeycloakIdentity.objects.get_or_create(
                    user=user, defaults={"sub": claims["sub"]}
                )
        except IntegrityError:
            # This sub was linked to another user a moment ago.
            identity = None
        if identity is None or identity.sub != claims["sub"]:
            # The user is linked to another Keycloak account: a race of two
            # first sign-ins. Never let one account into another's user.
            logger.warning("Keycloak sign-in refused: %s is linked elsewhere", user)
            raise PermissionDenied
        # Profile fields follow Keycloak; groups are left to the panel.
        # A name too long for its column is cut; an email is not, since a
        # cut address is somebody else's or nobody's.
        user.email = fit(claims.get("email"), user, "email", cut=False)
        user.first_name = fit(claims.get("given_name"), user, "first_name")
        user.last_name = fit(claims.get("family_name"), user, "last_name")
        user.save(update_fields=["email", "first_name", "last_name"])
        return user

    def get_user(self, user_id):
        # The only backend with SSO on, so it also has ModelBackend's duty:
        # a user switched off in the panel loses the session at once.
        user = super().get_user(user_id)
        return user if user is not None and user.is_active else None


def fit(value, user, field, cut=True):
    """A claim for a user column: as is, cut to length, or empty if it cannot fit."""
    value = value or ""
    max_length = user._meta.get_field(field).max_length
    if len(value) <= max_length:
        return value
    return value[:max_length] if cut else ""


def keycloak_logout_url(request):
    """End the Keycloak session too, otherwise SSO signs the user straight back in."""
    params = {
        "client_id": settings.OIDC_RP_CLIENT_ID,
        # Must be on the client's list of post-logout redirect URIs in Keycloak.
        "post_logout_redirect_uri": settings.OIDC_POST_LOGOUT_REDIRECT_URL
        or request.build_absolute_uri("/"),
    }
    id_token = request.session.get("oidc_id_token")
    if id_token:
        params["id_token_hint"] = id_token
    return f"{settings.OIDC_OP_LOGOUT_ENDPOINT}?{urlencode(params)}"
