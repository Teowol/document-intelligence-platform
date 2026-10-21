from pathlib import Path

from allauth.account.models import EmailAddress
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views.generic import UpdateView, View

from .forms import ProfileForm
from .permissions import require_admin


class ProfileView(LoginRequiredMixin, UpdateView):
    template_name = "accounts/profile.html"
    form_class = ProfileForm
    success_url = reverse_lazy("accounts:profile")

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user_role"] = self.request.user.get_role_display()
        name = self.request.user.get_full_name().strip() or self.request.user.username
        context["profile_name"] = name
        context["profile_initials"] = "".join(part[0] for part in name.split()[:2]).upper()
        context["document_count"] = self.request.user.documents.count()
        context["chat_count"] = self.request.user.qahistory_set.count()
        context["email_verified"] = EmailAddress.objects.filter(
            user=self.request.user, email__iexact=self.request.user.email, verified=True,
        ).exists()
        return context

    def form_valid(self, form):
        with transaction.atomic():
            if form.cleaned_data.get("remove_avatar"):
                form.instance.avatar = None
            response = super().form_valid(form)
            old_name = form.previous_avatar_name
            if old_name and old_name != self.object.avatar.name:
                transaction.on_commit(lambda: form.avatar_storage.delete(old_name))
        messages.success(self.request, _("Your profile has been updated."))
        return response


class ProfileAvatarView(LoginRequiredMixin, View):
    def get(self, request):
        avatar = request.user.avatar
        types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
        content_type = types.get(Path(avatar.name or "").suffix.lower())
        if not avatar or not content_type:
            raise Http404
        try:
            source = avatar.open("rb")
        except (OSError, ValueError) as exc:
            raise Http404 from exc
        response = FileResponse(source, content_type=content_type)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


@require_admin
def admin_only_demo(request):
    """Demo view proving @require_admin blocks non-admins (tested in Phase 2 DoD)."""
    return render(request, "accounts/admin_only.html")
