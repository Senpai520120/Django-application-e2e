"""Audit log of role changes."""

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models


class RoleChange(models.Model):
    """Who granted or revoked which role, and to whom."""

    ACTION_ADDED = "added"
    ACTION_REMOVED = "removed"
    ACTION_CHOICES = [
        (ACTION_ADDED, "granted"),
        (ACTION_REMOVED, "revoked"),
    ]

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="role_changes_made",
        verbose_name="changed by",
    )
    target = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="role_changes_received",
        verbose_name="target",
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="role_changes",
        verbose_name="role",
    )
    # Names are copied as plain text so a record outlives the group or the user.
    group_name = models.CharField("role name", max_length=150)
    target_username = models.CharField("target username", max_length=150)
    action = models.CharField("action", max_length=16, choices=ACTION_CHOICES)
    created_at = models.DateTimeField("created at", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "role change"
        verbose_name_plural = "role changes"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        actor = self.actor.username if self.actor else "system"
        verb = self.get_action_display()
        return f"{actor}: role {self.group_name} {verb} for {self.target_username}"

    @classmethod
    def log_diff(cls, *, actor, target, before, after):
        """Record the difference between two Group sets. Returns the created rows."""
        added = sorted(set(after) - set(before), key=lambda group: group.name)
        removed = sorted(set(before) - set(after), key=lambda group: group.name)

        entries = [
            cls(
                actor=actor,
                target=target,
                target_username=target.username,
                group=group,
                group_name=group.name,
                action=action,
            )
            for group, action in (
                *((group, cls.ACTION_ADDED) for group in added),
                *((group, cls.ACTION_REMOVED) for group in removed),
            )
        ]
        if entries:
            cls.objects.bulk_create(entries)
        return entries
