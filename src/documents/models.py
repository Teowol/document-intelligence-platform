from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from pgvector.django import VectorField

EMBEDDING_DIMENSIONS = 1536  # text-embedding-3-small output size


class Document(models.Model):
    """
    An uploaded document owned by a user.

    Status machine (Phase 4 drives the transitions via Celery):
        uploaded -> processing -> ready
                          \-------> error
    """

    class Status(models.TextChoices):
        UPLOADED = "uploaded", _("Uploaded")
        PROCESSING = "processing", _("Processing")
        READY = "ready", _("Ready")
        ERROR = "error", _("Error")

    class DocType(models.TextChoices):
        PDF = "pdf", "PDF"
        XLSX = "xlsx", "Excel"
        CSV = "csv", "CSV"
        TXT = "txt", _("Text")
        MD = "md", "Markdown"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    file = models.FileField(upload_to="documents/%Y/%m/")
    original_filename = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    doc_type = models.CharField(
        max_length=5, choices=DocType.choices, db_index=True
    )
    mime_type = models.CharField(max_length=100, blank=True, default="")
    size_bytes = models.PositiveBigIntegerField(default=0)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.UPLOADED,
        db_index=True,
    )
    error_message = models.TextField(blank=True, default="")
    summaries = models.JSONField(default=dict, blank=True)
    is_public = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Document"
        verbose_name_plural = "Documents"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.title} [{self.status}]"

    def delete(self, *args, **kwargs):
        """Remove the stored file from disk along with the DB row."""
        self.file.delete(save=False)
        super().delete(*args, **kwargs)


class QAHistory(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    question = models.TextField()
    answer = models.TextField()
    sources = models.JSONField(default=list, blank=True)
    tool_rounds = models.PositiveSmallIntegerField(default=0)
    documents = models.ManyToManyField(Document, related_name="qa_history", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["owner", "-created_at"])]


class DocumentChunk(models.Model):
    """
    One searchable chunk of a document.

    Text/metadata are filled in Phase 5 (parsing + chunking); the embedding
    column is filled in Phase 6. Exists since Phase 1 for schema sanity.
    """

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    page_number = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    chunk_index = models.PositiveIntegerField(default=0)
    text = models.TextField()
    embedding = VectorField(
        dimensions=EMBEDDING_DIMENSIONS,
        blank=True,
        null=True,
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Document chunk"
        verbose_name_plural = "Document chunks"
        ordering = ["document", "chunk_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "chunk_index"],
                name="unique_chunk_index_per_document",
            ),
        ]

    def __str__(self):
        return f"Chunk {self.chunk_index} of {self.document_id}"
