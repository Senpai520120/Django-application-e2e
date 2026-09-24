"""File manager views.

The views do not know where the files live: every conversation with the storage
goes through `files.storage.get_storage()`. A malformed path turns into
`SuspiciousFileOperation`, which Django answers with 400 on its own, so there
is nothing to catch here.
"""

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.template.defaultfilters import filesizeformat
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import FormView, TemplateView

from files.access import FileManagerAccessMixin
from files.forms import FolderForm, RenameForm, UploadForm
from files.paths import breadcrumbs, join_path, normalize_path, parent_path
from files.storage import StorageError, get_storage


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

        saved = 0
        for item in uploaded:
            name = item.name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            try:
                self.storage.save(join_path(path, name), item)
            except StorageError as error:
                messages.error(
                    self.request,
                    _("%(name)s: %(error)s") % {"name": name, "error": error},
                )
            else:
                saved += 1

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
            self.storage.rename(path, form.cleaned_data["new_name"])
        except StorageError as error:
            messages.error(self.request, str(error))
            return self.form_invalid(form)

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
