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
    files = MultipleFileField(label=_("Files"))

    def clean_files(self):
        uploaded = self.cleaned_data["files"]
        limit = settings.FILE_MANAGER["MAX_FILE_SIZE"]

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
