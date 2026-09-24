"""Root URLconf of the project."""

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
