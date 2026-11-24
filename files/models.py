"""What the app keeps about uploaded files in its own database."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class GroupingRule(models.Model):
    """The column a table file is grouped by in Airflow.

    Airflow reads these rows through the grouping-rules API (views.py) and
    groups each new file by its rule's column.
    """

    # The file's path inside the file manager, the same one Airflow sees.
    path = models.CharField(_("path"), max_length=1024, unique=True)
    # Empty: Airflow picks the first text column of the file.
    group_by = models.CharField(_("group by column"), max_length=255, blank=True)
    # Math per group, as [{"op": "sum", "column": "clicks"}, ...]; ops come
    # from files.pipeline.AGGREGATIONS. The columns are checked by Airflow,
    # which is the one to read the file.
    aggregations = models.JSONField(_("aggregations"), default=list, blank=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["path"]
        verbose_name = _("grouping rule")
        verbose_name_plural = _("grouping rules")

    def __str__(self):
        return f"{self.path} → {self.group_by or '(first text column)'}"
