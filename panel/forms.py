from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group, User
from django.utils.translation import gettext_lazy as _

from accounts.permissions import ADMIN_GROUP_NAME


def roles_field(**kwargs):
    """Checkboxes listing every role."""
    kwargs.setdefault("label", _("Roles"))
    kwargs.setdefault("required", False)
    return forms.ModelMultipleChoiceField(
        queryset=Group.objects.order_by("name"),
        widget=forms.CheckboxSelectMultiple,
        help_text=_("Tick the roles this user should hold."),
        **kwargs,
    )


class UserRolesForm(forms.ModelForm):
    groups = roles_field()

    class Meta:
        model = User
        fields = ["groups"]

    def __init__(self, *args, editor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.editor = editor

    def clean_groups(self):
        """Keep an admin from locking themselves out of the panel."""
        groups = self.cleaned_data["groups"]
        editing_self = self.editor is not None and self.editor.pk == self.instance.pk
        if not editing_self:
            return groups

        keeps_access = (
            self.editor.is_superuser
            or self.editor.is_staff
            or any(group.name == ADMIN_GROUP_NAME for group in groups)
        )
        if not keeps_access:
            raise forms.ValidationError(
                _(
                    "You cannot take the admin role from yourself: "
                    "you would lose access to the panel."
                )
            )
        return groups


class PanelUserCreationForm(UserCreationForm):
    """Built on UserCreationForm: password validation and hashing come with it."""

    email = forms.EmailField(label=_("Email"), required=False)
    groups = roles_field()

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name", "groups")
