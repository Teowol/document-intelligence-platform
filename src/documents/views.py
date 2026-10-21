import logging
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.translation import get_language, gettext as _
from django.views.generic import DeleteView, DetailView, ListView, TemplateView, View
from django.views.generic.edit import CreateView

from accounts.models import CustomUser

from .ai_engine import search_semantic
from .forms import DocumentUploadForm, QAQuestionForm
from .models import Document, DocumentChunk, QAHistory
from .preview import build_preview
from .qa import answer_question
from .ratelimit import require_rate_limit
from .tasks import process_document
from .summary import generate_summary
from .validators import sanitize_filename, validate_upload

logger = logging.getLogger(__name__)


def _visible_document(user, pk):
    doc = get_object_or_404(Document, pk=pk)
    if doc.owner_id == user.pk or doc.is_public or _is_admin(user):
        return doc
    raise PermissionDenied("You do not have permission to view this document.")


def _bust_dashboard_cache(user_pk: int) -> None:
    """Invalidate the per-user dashboard KPI cache after a data change."""
    cache.delete(f"dashboard_kpi_{user_pk}")


def _visible_history(user):
    history = QAHistory.objects.filter(owner=user)
    if not _is_admin(user):
        inaccessible = Document.objects.exclude(Q(owner=user) | Q(is_public=True))
        history = history.exclude(documents__in=inaccessible)
    return history


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
        if kpi is None or "type_breakdown" not in kpi:
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
                "new_this_week": kpi["new_this_week"],
                "type_breakdown": kpi["type_breakdown"],
                "recent_chats": _visible_history(user)[:3],
                "recent_documents": docs_qs.select_related(
                    "owner"
                ).order_by("-created_at")[:6],
            }
        )
        return context

    @staticmethod
    def _compute_kpis(docs_qs, user):
        """Aggregate-heavy numbers; kept off the hot path via cache."""
        totals = docs_qs.aggregate(
            total_docs=Count("pk"), total_size=Sum("size_bytes"),
            processed=Count("pk", filter=Q(status=Document.Status.READY)),
            processing=Count("pk", filter=Q(status=Document.Status.PROCESSING)),
            uploaded=Count("pk", filter=Q(status=Document.Status.UPLOADED)),
            errored=Count("pk", filter=Q(status=Document.Status.ERROR)),
            new_this_week=Count("pk", filter=Q(created_at__gte=timezone.now() - timedelta(days=7))),
        )
        total_docs = totals["total_docs"]
        visible_chunks = (
            DocumentChunk.objects.filter(
                document__in=docs_qs.values_list("id", flat=True)
            ).count()
        )
        formats = dict(Document.DocType.choices)
        type_breakdown = [
            {"label": formats[item["doc_type"]], "count": item["count"],
             "percent": round(item["count"] / total_docs * 100) if total_docs else 0}
            for item in docs_qs.order_by().values("doc_type").annotate(count=Count("pk")).order_by("-count", "doc_type")
        ]
        return {
            "visible_chunks": visible_chunks,
            "total_docs": total_docs,
            "total_size": totals["total_size"] or 0,
            "processed": totals["processed"],
            "processing": totals["processing"],
            "uploaded": totals["uploaded"],
            "errored": totals["errored"],
            "ready_rate": round(totals["processed"] / total_docs * 100) if total_docs else 0,
            "new_this_week": totals["new_this_week"],
            "type_breakdown": type_breakdown,
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
        messages.success(request, _("Document queued for re-processing."))
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

    def wants_json(self):
        return self.request.headers.get("Accept") == "application/json"

    def form_invalid(self, form):
        if self.wants_json():
            return JsonResponse({"errors": [
                {"field": name, "label": str(form.fields[name].label or name) if name in form.fields else str(_("Upload")),
                 "messages": [str(error) for error in errors]}
                for name, errors in form.errors.items()
            ]}, status=400)
        return super().form_invalid(form)

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
        messages.success(self.request, _("Document uploaded; processing started."))
        if self.wants_json():
            return JsonResponse({"url": reverse("documents:detail", args=[doc.pk])}, status=201)
        return redirect("documents:detail", pk=doc.pk)


class DocumentDetailView(LoginRequiredMixin, DetailView):
    model = Document
    template_name = "documents/document_detail.html"

    def get_object(self, queryset=None):
        return _visible_document(self.request.user, self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["chunks"] = self.object.chunks.order_by("chunk_index")[:5]
        context["chunk_count"] = self.object.chunks.count()
        language = "tr" if get_language().startswith("tr") else "en"
        context["summary"] = self.object.summaries.get(language)
        try:
            context["preview"] = build_preview(self.object, self.request.GET.get("sheet"))
        except Exception:
            logger.exception("Preview failed for document %s", self.object.pk)
            context["preview"] = {"kind": "unavailable"}
        return context


class DocumentSummaryView(LoginRequiredMixin, View):
    def post(self, request, pk):
        document = _visible_document(request.user, pk)
        language = "tr" if get_language().startswith("tr") else "en"
        url = f"{reverse('documents:detail', args=[pk])}?summary=1#summary-section"
        if document.status != Document.Status.READY:
            messages.info(request, _("The summary will be available after processing finishes."))
            return redirect(url)
        if language in document.summaries:
            return redirect(url)
        try:
            require_rate_limit(request.user, key="summary", limit=5, window=60)
        except PermissionDenied:
            messages.error(request, _("Too many summary requests. Please try again shortly."))
            return redirect(url)
        try:
            summary = generate_summary(document, language)
            with transaction.atomic():
                current = Document.objects.select_for_update().get(pk=pk)
                if current.updated_at != document.updated_at or current.status != Document.Status.READY:
                    raise ValueError("Document changed while generating the summary.")
                current.summaries[language] = summary
                current.save(update_fields=["summaries"])
        except Exception:
            logger.exception("Summary failed for document %s", pk)
            messages.error(request, _("Could not create the summary. Please try again."))
        return redirect(url)


class DocumentStatusView(LoginRequiredMixin, View):
    def get(self, request, pk):
        document = _visible_document(request.user, pk)
        state = document.status
        if state == Document.Status.READY:
            counts = document.chunks.aggregate(
                total=Count("pk"), embedded=Count("pk", filter=Q(embedding__isnull=False)),
            )
            state = "ready" if counts["total"] and counts["total"] == counts["embedded"] else "embedding"
        stages = {"uploaded": 1, "processing": 2, "embedding": 3, "ready": 4, "error": 0}
        labels = {
            "uploaded": _("Waiting for processing"), "processing": _("Extracting document text"),
            "embedding": _("Preparing semantic search"), "ready": _("Your document is ready"),
            "error": _("Processing failed. You can retry from file information."),
        }
        response = JsonResponse({
            "document_status": document.status,
            "state": state, "stage": stages[state], "label": labels[state],
            "finished": state in {"ready", "error"}, "text_ready": document.status == Document.Status.READY,
        })
        response["Cache-Control"] = "private, no-store"
        return response


class DocumentFileView(LoginRequiredMixin, View):
    """Stream originals through the same permissions as the document page."""

    def get(self, request, pk):
        document = _visible_document(request.user, pk)
        try:
            source = document.file.open("rb")
        except (OSError, ValueError) as exc:
            raise Http404("File is unavailable.") from exc
        content_types = {
            "pdf": "application/pdf",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "csv": "text/csv",
            "txt": "text/plain",
            "md": "text/plain",
        }
        response = FileResponse(
            source,
            as_attachment=request.GET.get("download") == "1" or document.doc_type != "pdf",
            filename=document.original_filename,
            content_type=content_types.get(document.doc_type, "application/octet-stream"),
        )
        response["X-Frame-Options"] = "SAMEORIGIN"
        response["Cache-Control"] = "private, no-store"
        return response


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
    template_name = "documents/qa.html"

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    def history_queryset(self):
        return _visible_history(self.request.user)

    def get(self, request, *args, **kwargs):
        if request.GET.get("history") == "1":
            history = self.history_queryset()
            selected = request.GET.get("chat")
            return JsonResponse({
                "entries": [
                    {"id": entry.pk, "question": entry.question,
                     "url": f"{reverse('documents:ask')}?chat={entry.pk}"}
                    for entry in history[:50]
                ],
                "selected_exists": not selected or (
                    selected.isdigit() and history.filter(pk=selected).exists()
                ),
            })
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["history"] = self.history_queryset()[:50]
        context["question"] = ""
        context["result"] = None
        selected = self.request.GET.get("chat")
        if selected:
            if not selected.isdigit():
                raise Http404
            entry = get_object_or_404(self.history_queryset(), pk=selected)
            context.update(question=entry.question, result=entry, selected_chat=entry.pk)
        return context

    def post(self, request, *args, **kwargs):
        form = QAQuestionForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form), status=400)
        question = form.cleaned_data["q"]
        try:
            require_rate_limit(request.user, key="qa", limit=10, window=60)
        except PermissionDenied:
            messages.error(request, _("Too many questions. Please try again shortly."))
            return self.render_to_response(self.get_context_data(form=form), status=429)
        try:
            result = answer_question(request.user, question, use_tools=True)
            source_ids = set(result.get("document_ids", []))
            with transaction.atomic():
                documents = Document.objects.select_for_update().filter(pk__in=source_ids)
                if not _is_admin(request.user):
                    documents = documents.filter(Q(owner=request.user) | Q(is_public=True))
                documents = list(documents)
                if len(documents) != len(source_ids):
                    raise ValueError("Source documents were removed or access changed.")
                entry = QAHistory.objects.create(
                    owner=request.user, question=question, answer=result["answer"],
                    sources=result.get("sources", []), tool_rounds=result.get("tool_rounds", 0),
                )
                entry.documents.set(documents)
        except Exception:
            logger.exception("Question answering failed for user %s", request.user.pk)
            messages.error(request, _("Could not answer the question. Please try again."))
            return self.render_to_response(self.get_context_data(form=form), status=502)
        return redirect(f"{reverse('documents:ask')}?chat={entry.pk}")
