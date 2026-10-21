from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["roles"] = self.request.user.groups.order_by("name")
        return context


class LoginFailedView(TemplateView):
    """Where a refused Keycloak sign-in lands. Public, so it cannot loop."""

    template_name = "accounts/login_failed.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if settings.OIDC_ENABLED:
            from accounts.oidc import keycloak_logout_url

            # Keycloak still remembers the refused user; without signing
            # out there, "sign in" would bring the same account back.
            context["sso_logout_url"] = keycloak_logout_url(self.request)
        return context
