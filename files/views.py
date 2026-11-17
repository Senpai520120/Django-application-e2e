"""File manager views.

The views do not know where the files live: every conversation with the storage
goes through `files.storage.get_storage()`. A malformed path turns into
`SuspiciousFileOperation`, which Django answers with 400 on its own, so there
is nothing to catch here.
"""

import secrets

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect
from django.template.defaultfilters import filesizeformat
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.http import urlencode
from django.utils.text import get_valid_filename
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import FormView, TemplateView

from files.access import FileManagerAccessMixin
from files.forms import FolderForm, RenameForm, UploadForm
from files.models import GroupingRule
from files.paths import breadcrumbs, join_path, normalize_path, parent_path
from files.pipeline import TABLE_FORMATS, processing_enabled, should_process
from files.storage import StorageError, get_storage
from files.uploads import oversized_uploads


def move_rules(old: str, new: str) -> None:
    """Rules of a renamed file, or of every file inside a renamed folder."""
    GroupingRule.objects.filter(path=old).update(path=new)
    prefix = f"{old}/"
    for rule in GroupingRule.objects.filter(path__startswith=prefix):
        rule.path = f"{new}/{rule.path[len(prefix) :]}"
        rule.save(update_fields=["path"])


def delete_rules(path: str) -> None:
    """Rules of a deleted file, or of every file inside a deleted folder."""
    GroupingRule.objects.filter(path=path).delete()
    GroupingRule.objects.filter(path__startswith=f"{path}/").delete()


def grouping_message(name: str, group_by: str) -> str:
    if group_by:
        return _("%(name)s will be grouped by %(column)s within a minute.") % {
            "name": name,
            "column": group_by,
        }
    return _("%(name)s will be grouped by its first text column within a minute.") % {
        "name": name
    }


def browse_url(path: str = "") -> str:
    """Link to the listing of a folder."""
    url = reverse("files:browse")
    return f"{url}?{urlencode({'path': path})}" if path else url


class FileManagerMixin(FileManagerAccessMixin):
    """Storage and current path, shared by every view of the section."""

    @cached_property
    def storage(self):
        return get_storage()

    @cached_property
    def path(self) -> str:
        raw = self.request.POST.get("path") or self.request.GET.get("path")
        return normalize_path(raw)

    def redirect_to(self, path: str):
        return redirect(browse_url(path))


class BrowseView(FileManagerMixin, TemplateView):
    template_name = "files/browse.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            entries = self.storage.list_dir(self.path)
        except StorageError as error:
            raise Http404(str(error)) from error

        context.update(
            path=self.path,
            entries=entries,
            crumbs=breadcrumbs(self.path),
            parent=parent_path(self.path),
            at_root=not self.path,
            folder_form=FolderForm(initial={"path": self.path}),
            upload_form=UploadForm(initial={"path": self.path}),
            backend=self.storage.__class__.__name__,
            max_file_size=filesizeformat(settings.FILE_MANAGER["MAX_FILE_SIZE"]),
            table_formats=TABLE_FORMATS if processing_enabled() else (),
        )
        return context


class FolderCreateView(FileManagerMixin, FormView):
    form_class = FolderForm

    def form_valid(self, form):
        target = join_path(form.cleaned_data["path"], form.cleaned_data["name"])
        try:
            self.storage.make_dir(target)
        except StorageError as error:
            messages.error(self.request, str(error))
        else:
            messages.success(
                self.request,
                _("Folder %(name)s created.") % {"name": form.cleaned_data["name"]},
            )
        return self.redirect_to(form.cleaned_data["path"])

    def form_invalid(self, form):
        for error in form.errors.values():
            messages.error(self.request, "; ".join(error))
        return self.redirect_to(self.path)

    def get(self, request, *args, **kwargs):
        return self.redirect_to(self.path)


class UploadView(FileManagerMixin, FormView):
    form_class = UploadForm

    def get_form_kwargs(self):
        # super() reads request.FILES, and parsing it fills oversized_uploads.
        kwargs = super().get_form_kwargs()
        kwargs["oversized"] = oversized_uploads(self.request)
        return kwargs

    def form_valid(self, form):
        path = form.cleaned_data["path"]
        uploaded = form.cleaned_data["files"]

        total_limit = settings.FILE_MANAGER["MAX_TOTAL_SIZE"]
        incoming = sum(item.size for item in uploaded)
        if self.storage.total_size() + incoming > total_limit:
            messages.error(
                self.request,
                _("Not enough room: the storage limit is %(limit)s.")
                % {"limit": filesizeformat(total_limit)},
            )
            return self.redirect_to(path)

        group_by = form.cleaned_data["group_by"]
        saved = 0
        for item in uploaded:
            # The name the storage would give the file anyway ("my sales.csv"
            # becomes "my_sales.csv"), so the rule below carries the same path.
            name = get_valid_filename(item.name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])
            target = join_path(path, name)
            # The rule goes in before the file: Airflow must never see a new
            # file without its column. A file already there is refused by
            # save() below, and its rule must stay as it is.
            ruled = should_process(name) and not self.storage.exists(target)
            if ruled:
                GroupingRule.objects.update_or_create(
                    path=target, defaults={"group_by": group_by}
                )
            try:
                stored = self.storage.save(target, item)
            except StorageError as error:
                if ruled:
                    GroupingRule.objects.filter(path=target).delete()
                messages.error(
                    self.request,
                    _("%(name)s: %(error)s") % {"name": name, "error": error},
                )
                continue
            saved += 1
            if ruled:
                if stored != target:
                    move_rules(target, stored)
                messages.info(self.request, grouping_message(name, group_by))

        if saved:
            messages.success(
                self.request, _("Uploaded files: %(count)s.") % {"count": saved}
            )
        return self.redirect_to(path)

    def form_invalid(self, form):
        for error in form.errors.values():
            messages.error(self.request, "; ".join(error))
        return self.redirect_to(self.path)

    def get(self, request, *args, **kwargs):
        return self.redirect_to(self.path)


class RenameView(FileManagerMixin, FormView):
    form_class = RenameForm
    template_name = "files/rename.html"

    def get_initial(self):
        return {"path": self.path, "new_name": self.path.rsplit("/", 1)[-1]}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if not self.path:
            raise Http404("Nothing to rename.")
        if not self.storage.exists(self.path):
            raise Http404("File or folder not found.")
        context.update(
            path=self.path,
            name=self.path.rsplit("/", 1)[-1],
            parent=parent_path(self.path),
            is_dir=self.storage.is_dir(self.path),
        )
        return context

    def form_valid(self, form):
        path = form.cleaned_data["path"]
        try:
            new_path = self.storage.rename(path, form.cleaned_data["new_name"])
        except StorageError as error:
            messages.error(self.request, str(error))
            return self.form_invalid(form)
        move_rules(path, new_path)

        messages.success(
            self.request,
            _("Renamed to %(name)s.") % {"name": form.cleaned_data["new_name"]},
        )
        return self.redirect_to(parent_path(path))


class DeleteView(FileManagerMixin, TemplateView):
    template_name = "files/delete.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if not self.path:
            raise Http404("The root cannot be deleted.")
        if not self.storage.exists(self.path):
            raise Http404("File or folder not found.")

        context.update(
            path=self.path,
            name=self.path.rsplit("/", 1)[-1],
            parent=parent_path(self.path),
            is_dir=self.storage.is_dir(self.path),
        )
        return context

    def post(self, request, *args, **kwargs):
        parent = parent_path(self.path)
        try:
            self.storage.delete(self.path)
        except StorageError as error:
            messages.error(request, str(error))
        else:
            delete_rules(self.path)
            messages.success(
                request,
                _("Deleted: %(name)s.") % {"name": self.path.rsplit("/", 1)[-1]},
            )
        return self.redirect_to(parent)


class DownloadView(FileManagerMixin, View):
    def get(self, request, *args, **kwargs):
        if not self.path or self.storage.is_dir(self.path):
            raise Http404("File not found.")

        try:
            handle = self.storage.open(self.path)
        except StorageError as error:
            raise Http404(str(error)) from error

        name = self.path.rsplit("/", 1)[-1]
        # as_attachment: even html or exe leave as a download instead of
        # being executed or rendered by the browser.
        return FileResponse(handle, as_attachment=True, filename=name)


class GroupingRulesView(View):
    """The grouping rules as JSON, for the watch_uploads DAG in Airflow.

    Airflow is a program, not a person, so instead of a login it sends the
    shared PIPELINE_API_TOKEN. With no token set the API does not exist.
    """

    def get(self, request, *args, **kwargs):
        token = settings.PIPELINE_API_TOKEN
        if not token:
            raise Http404("The grouping rules API is off.")
        scheme, _space, given = request.headers.get("Authorization", "").partition(" ")
        # compare_digest takes as long for a near miss as for a far one, so
        # the token cannot be guessed letter by letter from response times.
        if scheme.lower() != "bearer" or not secrets.compare_digest(
            given.encode(), token.encode()
        ):
            return JsonResponse(
                {"detail": "A valid Bearer token is required."},
                status=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        rules = list(GroupingRule.objects.values("path", "group_by"))
        return JsonResponse(rules, safe=False)
