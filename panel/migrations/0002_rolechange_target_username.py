import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def fill_target_username(apps, schema_editor):
    RoleChange = apps.get_model("panel", "RoleChange")
    for change in RoleChange.objects.select_related("target").iterator():
        if change.target_id:
            change.target_username = change.target.username
            change.save(update_fields=["target_username"])


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("panel", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="rolechange",
            name="target_username",
            field=models.CharField(
                default="", max_length=150, verbose_name="кому (логин)"
            ),
            preserve_default=False,
        ),
        migrations.RunPython(fill_target_username, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="rolechange",
            name="target",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="role_changes_received",
                to=settings.AUTH_USER_MODEL,
                verbose_name="кому",
            ),
        ),
        migrations.AlterField(
            model_name="rolechange",
            name="group_name",
            field=models.CharField(max_length=150, verbose_name="имя роли"),
        ),
    ]
