"""Views of the /manage/ panel."""

from django.contrib import messages
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from accounts.mixins import AdminRequiredMixin
from panel.forms import PanelUserCreationForm, UserRolesForm
from panel.models import RoleChange


def safe_next(request):
    """Return address from ?next=, but only when it points back at this site."""
    next_url = request.POST.get("next") or request.GET.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return ""


class UserListView(AdminRequiredMixin, ListView):
    """Search through ?q= plus pagination."""

    template_name = "panel/user_list.html"
    context_object_name = "users"
    paginate_by = 10

    def get_queryset(self):
        queryset = User.objects.prefetch_related("groups").order_by("username")
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(username__icontains=query)
                | Q(email__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "").strip()
        return context


class RoleListView(AdminRequiredMixin, ListView):
    template_name = "panel/role_list.html"
    context_object_name = "roles"
    queryset = Group.objects.annotate(members_count=Count("user")).order_by("name")


class UserRolesUpdateView(AdminRequiredMixin, UpdateView):
    model = User
    form_class = UserRolesForm
    template_name = "panel/user_roles_form.html"
    context_object_name = "target_user"
    success_url = reverse_lazy("panel:user_list")

    def get_object(self, queryset=None):
        target = super().get_object(queryset)
        if target.is_superuser and not self.request.user.is_superuser:
            raise PermissionDenied(
                _("Only a superuser may change the roles of a superuser.")
            )
        return target

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["editor"] = self.request.user
        return kwargs

    def get_success_url(self):
        """Go back where we came from: the list may have had a query and a page."""
        return safe_next(self.request) or str(self.success_url)

    @transaction.atomic
    def form_valid(self, form):
        before = set(self.object.groups.all())
        response = super().form_valid(form)
        after = set(self.object.groups.all())

        changes = RoleChange.log_diff(
            actor=self.request.user,
            target=self.object,
            before=before,
            after=after,
        )
        if changes:
            messages.success(
                self.request,
                _("Roles of %(username)s updated (changes: %(count)s).")
                % {"username": self.object.username, "count": len(changes)},
            )
        else:
            messages.info(
                self.request,
                _("Roles of %(username)s are unchanged.")
                % {"username": self.object.username},
            )
        return response


class UserCreateView(AdminRequiredMixin, CreateView):
    model = User
    form_class = PanelUserCreationForm
    template_name = "panel/user_form.html"
    success_url = reverse_lazy("panel:user_list")

    @transaction.atomic
    def form_valid(self, form):
        response = super().form_valid(form)
        RoleChange.log_diff(
            actor=self.request.user,
            target=self.object,
            before=set(),
            after=set(self.object.groups.all()),
        )
        messages.success(
            self.request,
            _("User %(username)s created.") % {"username": self.object.username},
        )
        return response


class UserToggleActiveView(AdminRequiredMixin, View):
    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        if target.is_superuser and not request.user.is_superuser:
            raise PermissionDenied(_("Only a superuser may switch off a superuser."))

        if target == request.user:
            messages.error(request, _("You cannot switch yourself off."))
        else:
            target.is_active = not target.is_active
            target.save(update_fields=["is_active"])
            state = _("enabled") if target.is_active else _("disabled")
            messages.success(
                request,
                _("User %(username)s %(state)s.")
                % {"username": target.username, "state": state},
            )
        return redirect(safe_next(request) or "panel:user_list")


class AuditLogView(AdminRequiredMixin, ListView):
    template_name = "panel/audit_list.html"
    context_object_name = "changes"
    paginate_by = 20
    queryset = RoleChange.objects.select_related("actor", "target")
