from django.conf import settings
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy
from django.views.generic import RedirectView

from accounts.views import HomeView, LoginFailedView

if settings.OIDC_ENABLED:
    from mozilla_django_oidc.views import OIDCLogoutView

    # /login/ keeps working as an address: it hands over to Keycloak, ?next= included.
    login_view = RedirectView.as_view(
        url=reverse_lazy("oidc_authentication_init"), query_string=True
    )
    # Also ends the Keycloak session, see accounts.oidc.keycloak_logout_url.
    logout_view = OIDCLogoutView.as_view()
else:
    login_view = auth_views.LoginView.as_view(redirect_authenticated_user=True)
    logout_view = auth_views.LogoutView.as_view()

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("login/", login_view, name="login"),
    path("login/failed/", LoginFailedView.as_view(), name="login_failed"),
    path("logout/", logout_view, name="logout"),
]
