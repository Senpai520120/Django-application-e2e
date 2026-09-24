from django.contrib import admin

from panel.models import RoleChange


@admin.register(RoleChange)
class RoleChangeAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "group_name", "target_username")
    list_filter = ("action", "group_name")
    search_fields = ("actor__username", "target_username", "group_name")
    readonly_fields = (
        "actor",
        "target",
        "target_username",
        "group",
        "group_name",
        "action",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
