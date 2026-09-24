from accounts.permissions import is_admin


def panel_access(request):
    """Whether the header should show a link to the admin panel."""
    return {"is_panel_admin": is_admin(request.user)}
