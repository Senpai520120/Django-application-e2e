from django.contrib.auth import views as auth_views
from django.urls import path

from accounts.views import HomeView

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path(
        "login/",
        auth_views.LoginView.as_view(redirect_authenticated_user=True),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
