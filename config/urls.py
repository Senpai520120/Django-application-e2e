"""Root URLconf of the project."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("accounts.urls")),
    path("manage/", include("panel.urls")),
    path("files/", include("files.urls")),
    # Django's stock admin is kept for reference only; the assignment is
    # solved by the custom panel at /manage/.
    path("admin/", admin.site.urls),
]

if settings.OIDC_ENABLED:
    # /oidc/authenticate/ sends the browser to Keycloak, /oidc/callback/ takes it back.
    urlpatterns.append(path("oidc/", include("mozilla_django_oidc.urls")))
