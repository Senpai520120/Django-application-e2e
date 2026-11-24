"""What the app keeps about uploaded files in its own database."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class GroupingRule(models.Model):
    """How a table file is grouped in Airflow: the column and the math.

    Airflow reads these rows through the grouping-rules API (views.py). A rule
    is made as a draft when the file is uploaded; the user then picks the
    column and the math on the grouping page, and only then does Airflow
    process the file.
    """

    # The file's path inside the file manager, the same one Airflow sees.
    path = models.CharField(_("path"), max_length=1024, unique=True)
    # Empty: Airflow picks the first text column of the file.
    group_by = models.CharField(_("group by column"), max_length=255, blank=True)
    # Math per group, as [{"op": "sum", "column": "clicks"}, ...]; ops come
    # from files.pipeline.AGGREGATIONS, columns from the file itself (the
    # grouping page offers only those). Airflow checks them again.
    aggregations = models.JSONField(_("aggregations"), default=list, blank=True)
    # False from the upload until the user saves the grouping page: Airflow
    # leaves the file alone until then, so DuckDB never gets a result by a
    # column nobody chose.
    configured = models.BooleanField(_("configured"), default=False)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["path"]
        verbose_name = _("grouping rule")
        verbose_name_plural = _("grouping rules")

    def __str__(self):
        return f"{self.path} → {self.group_by or '(first text column)'}"
