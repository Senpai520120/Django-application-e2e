from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("files", "0003_grouping_rule_configured"),
    ]

    operations = [
        migrations.AddField(
            model_name="groupingrule",
            name="revision",
            field=models.PositiveIntegerField(default=0, verbose_name="revision"),
        ),
    ]
