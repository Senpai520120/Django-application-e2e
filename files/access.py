"""Access rule for the file manager.

The section is shared by the whole team, so it is open to every signed-in user,
unlike the /manage/ panel, which requires the admin role. To hand the files to
administrators only, swap the base class here for
`accounts.mixins.AdminRequiredMixin`: the views inherit from this mixin and
check permissions nowhere else.
"""

from django.contrib.auth.mixins import LoginRequiredMixin


class FileManagerAccessMixin(LoginRequiredMixin):
    """Anonymous goes to login; any signed-in user may work with the files."""
