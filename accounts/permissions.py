"""Who counts as an admin. Roles are plain built-in auth.Group objects."""

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

ADMIN_GROUP_NAME = "admin"
USER_GROUP_NAME = "user"

DEFAULT_GROUP_NAMES = (ADMIN_GROUP_NAME, USER_GROUP_NAME)


def is_admin(user: AbstractBaseUser | AnonymousUser) -> bool:
    """Member of the admin group, a staff member, or a superuser.

    The answer is cached on the user object: within a single request the check
    is called by both the mixin and the context processor, and one database
    query is enough for both.
    """
    cached = getattr(user, "_is_panel_admin", None)
    if cached is not None:
        return cached

    if not user.is_authenticated:
        result = False
    elif user.is_superuser or user.is_staff:
        result = True
    else:
        result = user.groups.filter(name=ADMIN_GROUP_NAME).exists()

    user._is_panel_admin = result
    return result
