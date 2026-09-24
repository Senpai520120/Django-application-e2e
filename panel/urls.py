from django.urls import path

from panel import views

app_name = "panel"

urlpatterns = [
    path("", views.UserListView.as_view(), name="user_list"),
    path("users/new/", views.UserCreateView.as_view(), name="user_create"),
    path(
        "users/<int:pk>/roles/", views.UserRolesUpdateView.as_view(), name="user_roles"
    ),
    path(
        "users/<int:pk>/toggle-active/",
        views.UserToggleActiveView.as_view(),
        name="user_toggle_active",
    ),
    path("roles/", views.RoleListView.as_view(), name="role_list"),
    path("audit/", views.AuditLogView.as_view(), name="audit_log"),
]
