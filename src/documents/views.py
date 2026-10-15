from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import DeleteView, DetailView, ListView, TemplateView
from django.views.generic.edit import CreateView

from accounts.models import CustomUser

from .ai_engine import search_semantic
from .forms import DocumentUploadForm
from .models import Document
from .qa import answer_question
from .tasks import process_document
from .validators import sanitize_filename, validate_upload


def _is_admin(user) -> bool:
    return user.is_superuser or user.role == CustomUser.Roles.ADMIN


def _is_editor(user) -> bool:
    return user.is_superuser or user.role in (
        CustomUser.Roles.ADMIN,
        CustomUser.Roles.EDITOR,
    )


class DocumentListView(LoginRequiredMixin, ListView):
    """Own documents plus public ones (admins see everything)."""

    model = Document
    template_name = "documents/document_list.html"
    paginate_by = 20

    def get_queryset(self):
        user = self.request.user
        if _is_admin(user):
            return Document.objects.select_related("owner")
        return Document.objects.filter(Q(owner=user) | Q(is_public=True)).select_related(
            "owner"
        )


class DocumentUploadView(LoginRequiredMixin, CreateView):
    """
    Secure upload: server-side size limit + magic-byte type check.
    The browser-reported content type is never trusted.
    """

    model = Document
    form_class = DocumentUploadForm
    template_name = "documents/document_form.html"
    success_url = reverse_lazy("documents:list")

    def form_valid(self, form):
        file = form.cleaned_data["file"]
        try:
            doc_type, mime = validate_upload(file)
        except ValidationError as exc:
            form.add_error("file", exc.message)
            return self.form_invalid(form)

        doc = form.save(commit=False)
        doc.owner = self.request.user
        doc.doc_type = doc_type
        doc.mime_type = mime
        doc.size_bytes = file.size
        doc.original_filename = sanitize_filename(file.name)
        doc.status = Document.Status.UPLOADED
        doc.save()
        # Phase 4: hand off to the background worker; the request returns fast.
        process_document.delay(doc.pk)
        messages.success(self.request, "Document uploaded; processing started.")
        return redirect("documents:detail", pk=doc.pk)


class DocumentDetailView(LoginRequiredMixin, DetailView):
    model = Document
    template_name = "documents/document_detail.html"

    def get_object(self, queryset=None):
        doc = get_object_or_404(Document, pk=self.kwargs["pk"])
        user = self.request.user
        if doc.owner_id == user.pk or doc.is_public or _is_admin(user):
            return doc
        raise PermissionDenied("Bu dokümanı görüntüleme yetkiniz yok.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["chunks"] = self.object.chunks.order_by("chunk_index")[:5]
        context["chunk_count"] = self.object.chunks.count()
        return context


class DocumentDeleteView(LoginRequiredMixin, DeleteView):
    """Only the owner (or an admin) may delete; others get 403."""

    model = Document
    template_name = "documents/document_confirm_delete.html"
    success_url = reverse_lazy("documents:list")

    def get_object(self, queryset=None):
        doc = get_object_or_404(Document, pk=self.kwargs["pk"])
        user = self.request.user
        if doc.owner_id == user.pk or _is_admin(user):
            return doc
        raise PermissionDenied("Bu dokümanı silme yetkiniz yok.")


class DocumentSearchView(LoginRequiredMixin, TemplateView):
    """
    Semantic search UI (Phase 6). Runs a cosine top-k query scoped to the
    requesting user's permissions.
    """

    template_name = "documents/document_search.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        context["query"] = query
        context["results"] = []
        if query:
            try:
                context["results"] = search_semantic(
                    self.request.user, query, top_k=8
                )
            except Exception as exc:  # noqa: BLE001 - surface API errors in UI
                from django.contrib import messages as dj_messages

                dj_messages.error(
                    self.request, f"Semantic search failed: {exc}"
                )
        return context


class DocumentQAView(LoginRequiredMixin, TemplateView):
    """
    Phase 7: grounded question-answering UI. Runs the RAG + function-calling
    pipeline with RBAC-scoped tools, then shows the answer with citations.
    """

    template_name = "documents/qa.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        question = self.request.GET.get("q", "").strip()
        context["question"] = question
        context["result"] = None
        if question:
            try:
                context["result"] = answer_question(
                    self.request.user, question, use_tools=True
                )
            except Exception as exc:  # noqa: BLE001 - surface API errors in UI
                from django.contrib import messages as dj_messages

                dj_messages.error(
                    self.request, f"Question answering failed: {exc}"
                )
        return context
