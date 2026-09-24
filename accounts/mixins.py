from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from accounts.permissions import is_admin


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Anonymous goes to login, a signed-in non-admin gets 403 (AccessMixin)."""

    def test_func(self) -> bool:
        return is_admin(self.request.user)
