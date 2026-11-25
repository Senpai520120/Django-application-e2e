"""File manager forms.

Names arrive from the user, so every form runs them through `files.paths` —
the single place that decides what is allowed.
"""

from django import forms
from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.template.defaultfilters import filesizeformat
from django.utils.translation import gettext_lazy as _

from files.paths import MAX_NAME_LENGTH, clean_name, normalize_path
from files.pipeline import AGGREGATIONS, MAX_AGGREGATIONS, NUMERIC_ONLY, is_numeric


class PathField(forms.CharField):
    """Hidden field holding the path to a folder or a file."""

    widget = forms.HiddenInput

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)

    def clean(self, value):
        value = super().clean(value)
        try:
            return normalize_path(value)
        except SuspiciousFileOperation as error:
            raise forms.ValidationError(str(error)) from error


class NameField(forms.CharField):
    """A file or folder name already checked for forbidden characters."""

    def __init__(self, **kwargs):
        kwargs.setdefault("max_length", MAX_NAME_LENGTH)
        kwargs.setdefault("strip", True)
        super().__init__(**kwargs)

    def clean(self, value):
        value = super().clean(value)
        try:
            return clean_name(value)
        except SuspiciousFileOperation as error:
            raise forms.ValidationError(str(error)) from error


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Several files in one field, following the recipe from the Django docs."""

    def __init__(self, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"multiple": True}))
        super().__init__(**kwargs)

    def clean(self, data, initial=None):
        clean_single = super().clean
        if isinstance(data, (list, tuple)):
            return [clean_single(item, initial) for item in data]
        return [clean_single(data, initial)]


class FolderForm(forms.Form):
    path = PathField()
    name = NameField(label=_("Folder name"))


class RenameForm(forms.Form):
    path = PathField(required=True)
    new_name = NameField(label=_("New name"))


class UploadForm(forms.Form):
    path = PathField()
    # Not required at field level: a file dropped by SizeLimitUploadHandler
    # must be reported as too large, not as missing.
    files = MultipleFileField(label=_("Files"), required=False)

    def __init__(self, *args, oversized=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.oversized = list(oversized)

    def clean_files(self):
        uploaded = [item for item in self.cleaned_data["files"] if item]
        limit = settings.FILE_MANAGER["MAX_FILE_SIZE"]

        # Already stopped while arriving, so never written to disk.
        if self.oversized:
            raise forms.ValidationError(
                _("File %(name)s is larger than the allowed %(limit)s.")
                % {"name": self.oversized[0], "limit": filesizeformat(limit)}
            )
        if not uploaded:
            raise forms.ValidationError(
                self.fields["files"].error_messages["required"], code="required"
            )

        for item in uploaded:
            if item.size > limit:
                raise forms.ValidationError(
                    _("File %(name)s is larger than the allowed %(limit)s.")
                    % {"name": item.name, "limit": filesizeformat(limit)}
                )
            # The name comes from the browser and may carry a whole path.
            try:
                clean_name(item.name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])
            except SuspiciousFileOperation as error:
                raise forms.ValidationError(
                    _("File %(name)s: %(error)s") % {"name": item.name, "error": error}
                ) from error

        return uploaded


class GroupingForm(forms.Form):
    """The column to group a table file by and the math per group.

    Built from the file's own columns (files.pipeline.file_schema), so only
    real columns can be picked, and the number-only ops are offered for number
    columns only. A checkbox is "op:index" of the column, never a name typed
    by hand, and anything else sent is refused as an invalid choice.
    """

    path = PathField(required=True)

    def __init__(self, *args, schema: list[tuple[str, str]], **kwargs):
        super().__init__(*args, **kwargs)
        self.schema = schema
        self.fields["group_by"] = forms.ChoiceField(
            label=_("Group by"),
            choices=[(name, name) for name, _type in schema],
            widget=forms.RadioSelect,
            error_messages={"required": _("Choose the column to group by.")},
        )
        self.fields["aggregations"] = forms.MultipleChoiceField(
            label=_("Math per group"),
            choices=[(value, value) for value in self.allowed_values()],
            widget=forms.CheckboxSelectMultiple,
            required=False,
        )

    def allowed_values(self) -> list[str]:
        """Every "op:index" a checkbox may send, in table order."""
        return [
            f"{op}:{index}"
            for index, (_name, type_) in enumerate(self.schema)
            for op in AGGREGATIONS
            if op not in NUMERIC_ONLY or is_numeric(type_)
        ]

    def clean_aggregations(self):
        chosen = set(self.cleaned_data["aggregations"])
        result = []
        # Table order (by column, then by op), whatever order they came in.
        for value in self.allowed_values():
            if value in chosen:
                op, index = value.split(":")
                result.append({"op": op, "column": self.schema[int(index)][0]})
        if len(result) > MAX_AGGREGATIONS:
            raise forms.ValidationError(
                _("At most %(count)s aggregations.") % {"count": MAX_AGGREGATIONS}
            )
        return result

    @classmethod
    def initial_for(cls, schema, rule) -> dict:
        """What the page shows checked: the saved rule, or a sensible start."""
        names = [name for name, _type in schema]
        if rule is not None and rule.configured and rule.group_by in names:
            group_by = rule.group_by
        else:
            # The DAG's own default: the first text column, else the first.
            texts = [name for name, type_ in schema if type_.upper() == "VARCHAR"]
            group_by = (texts or names or [""])[0]
        index = {name: position for position, name in enumerate(names)}
        saved = rule.aggregations if rule is not None else []
        # Skip what a rule broken by hand holds: this page is where it is
        # mended, so it must open.
        aggregations = [
            f"{item['op']}:{index[item['column']]}"
            for item in (saved if isinstance(saved, list) else [])
            if isinstance(item, dict)
            and item.get("op") in AGGREGATIONS
            and item.get("column") in index
        ]
        return {"group_by": group_by, "aggregations": aggregations}
