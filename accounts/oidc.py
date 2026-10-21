"""Sign-in through Keycloak: who the user is.

Keycloak answers only "who you are". What the user may do stays in the panel:
roles are Django groups, and a user switched off in the panel cannot sign in
even with a valid Keycloak password (the callback view checks is_active).
"""

from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.models import Group
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from accounts.permissions import USER_GROUP_NAME


class KeycloakBackend(OIDCAuthenticationBackend):
    """Finds the Django user by the Keycloak username."""

    def filter_users_by_claims(self, claims):
        # By username, so the accounts that already exist in Django
        # (demo_admin and the rest) are the same people in Keycloak.
        username = claims.get("preferred_username")
        if not username:
            return self.UserModel.objects.none()
        return self.UserModel.objects.filter(username=username)

    def verify_claims(self, claims):
        return super().verify_claims(claims) and bool(claims.get("preferred_username"))

    def create_user(self, claims):
        # No password: this user can come in only through Keycloak.
        user = self.UserModel.objects.create_user(claims["preferred_username"])
        user.groups.add(Group.objects.get(name=USER_GROUP_NAME))
        return self.update_user(user, claims)

    def update_user(self, user, claims):
        # Profile fields follow Keycloak; groups are left to the panel.
        user.email = claims.get("email", "")
        user.first_name = claims.get("given_name", "")
        user.last_name = claims.get("family_name", "")
        user.save(update_fields=["email", "first_name", "last_name"])
        return user


def keycloak_logout_url(request):
    """End the Keycloak session too, otherwise SSO signs the user straight back in."""
    params = {
        "client_id": settings.OIDC_RP_CLIENT_ID,
        "post_logout_redirect_uri": request.build_absolute_uri("/"),
    }
    id_token = request.session.get("oidc_id_token")
    if id_token:
        params["id_token_hint"] = id_token
    return f"{settings.OIDC_OP_LOGOUT_ENDPOINT}?{urlencode(params)}"
