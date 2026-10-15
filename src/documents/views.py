from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import DeleteView, DetailView, ListView, TemplateView, View
from django.views.generic.edit import CreateView

from accounts.models import CustomUser

from .ai_engine import search_semantic
from .forms import DocumentUploadForm
from .models import Document, DocumentChunk
from .qa import answer_question
from .ratelimit import require_rate_limit
from .tasks import process_document
from .validators import sanitize_filename, validate_upload


def _bust_dashboard_cache(user_pk: int) -> None:
    """Invalidate the per-user dashboard KPI cache after a data change."""
    cache.delete(f"dashboard_kpi_{user_pk}")


class DashboardView(LoginRequiredMixin, TemplateView):
    """Overview page: KPIs, status breakdown, recent documents."""

    template_name = "documents/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        if _is_admin(user):
            docs_qs = Document.objects.all()
        else:
            docs_qs = Document.objects.filter(Q(owner=user) | Q(is_public=True))

        # Heavy aggregates are cached per user with a short TTL so frequent
        # dashboard visits don't re-scan the whole table every request.
        cache_key = f"dashboard_kpi_{user.pk}"
        kpi = cache.get(cache_key)
        if kpi is None:
            kpi = self._compute_kpis(docs_qs, user)
            cache.set(cache_key, kpi, timeout=30)

        context.update(
            {
                "visible_chunks": kpi["visible_chunks"],
                "total_docs": kpi["total_docs"],
                "total_size": kpi["total_size"],
                "processed": kpi["processed"],
                "processing": kpi["processing"],
                "uploaded": kpi["uploaded"],
                "errored": kpi["errored"],
                "ready_rate": kpi["ready_rate"],
                "recent_documents": docs_qs.select_related(
                    "owner"
                ).order_by("-created_at")[:6],
            }
        )
        return context

    @staticmethod
    def _compute_kpis(docs_qs, user):
        """Aggregate-heavy numbers; kept off the hot path via cache."""
        total_docs = docs_qs.count()
        size_summary = docs_qs.aggregate(total=Sum("size_bytes"))
        total_size = size_summary["total"] or 0
        visible_chunks = (
            DocumentChunk.objects.filter(
                document__in=docs_qs.values_list("id", flat=True)
            ).count()
        )
        processed = docs_qs.filter(status=Document.Status.READY).count()
        processing = docs_qs.filter(status=Document.Status.PROCESSING).count()
        uploaded = docs_qs.filter(status=Document.Status.UPLOADED).count()
        errored = docs_qs.filter(status=Document.Status.ERROR).count()
        return {
            "visible_chunks": visible_chunks,
            "total_docs": total_docs,
            "total_size": total_size,
            "processed": processed,
            "processing": processing,
            "uploaded": uploaded,
            "errored": errored,
            "ready_rate": round(processed / total_docs * 100) if total_docs else 0,
        }


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
    paginate_by = 12

    def get_queryset(self):
        user = self.request.user
        if _is_admin(user):
            queryset = Document.objects.select_related("owner")
        else:
            queryset = Document.objects.filter(Q(owner=user) | Q(is_public=True)).select_related("owner")
        # optional status filter from ?status=
        status = self.request.GET.get("status")
        if status in {s for s, _ in Document.Status.choices}:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_status"] = self.request.GET.get("status", "")
        return context


class DocumentReprocessView(LoginRequiredMixin, View):
    """Re-run the Celery pipeline for a document (owner/admin only)."""

    def post(self, request, *args, **kwargs):
        user = request.user
        doc = get_object_or_404(Document, pk=kwargs["pk"])
        if not (doc.owner_id == user.pk or _is_admin(user)):
            raise PermissionDenied("Bu dokümanı yeniden işleme yetkiniz yok.")
        if doc.status in (Document.Status.PROCESSING, Document.Status.UPLOADED):
            return redirect("documents:detail", pk=doc.pk)
        doc.status = Document.Status.UPLOADED
        doc.save(update_fields=["status", "updated_at"])
        process_document.delay(doc.pk)
        messages.success(request, "Document queued for re-processing.")
        return redirect("documents:detail", pk=doc.pk)


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
        _bust_dashboard_cache(doc.owner_id)
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

    def form_valid(self, form):
        owner_pk = self.object.owner_id
        response = super().form_valid(form)
        _bust_dashboard_cache(owner_pk)
        return response


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
                require_rate_limit(
                    self.request.user, key="search", limit=30, window=60
                )
                context["results"] = search_semantic(
                    self.request.user, query, top_k=8
                )
            except PermissionDenied:
                from django.contrib import messages as dj_messages
                from django.http import HttpResponse

                dj_messages.error(
                    self.request,
                    "Arama sınırına ulaşıldı. Kısa bir süre sonra tekrar deneyin.",
                )
                return HttpResponse("Rate-limited", status=429)
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
                require_rate_limit(
                    self.request.user, key="qa", limit=10, window=60
                )
                context["result"] = answer_question(
                    self.request.user, question, use_tools=True
                )
            except PermissionDenied:
                from django.contrib import messages as dj_messages
                from django.http import HttpResponse

                dj_messages.error(
                    self.request,
                    "Soru limitine ulaşıldı. Kısa bir süre sonra tekrar deneyin.",
                )
                return HttpResponse("Rate-limited", status=429)
            except Exception as exc:  # noqa: BLE001 - surface API errors in UI
                from django.contrib import messages as dj_messages

                dj_messages.error(
                    self.request, f"Question answering failed: {exc}"
                )
        return context
