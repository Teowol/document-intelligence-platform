"""Background tasks for document processing.

Pipeline: process_document (parse + chunk, Phase 5) -> embed_document
(embeddings, Phase 6). The status machine is production-shaped:

    uploaded -> processing -> ready
                        \\-----> error (parsing failure or unexpected crash)
"""

import logging

from celery import shared_task
from django.db import transaction

from .ai_engine import embed_chunks_batch
from .models import Document, DocumentChunk
from .parsing import ParsingError, parse_and_chunk

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def process_document(self, document_id: int) -> str:
    """Parse, normalize and chunk a document; persist DocumentChunk rows."""
    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        logger.warning("process_document: document %s vanished; skipping", document_id)
        return "missing"

    doc.status = Document.Status.PROCESSING
    doc.summaries = {}
    doc.save(update_fields=["status", "summaries", "updated_at"])

    try:
        doc.file.open("rb")
        try:
            chunks = parse_and_chunk(doc.file, doc.doc_type)
        finally:
            doc.file.close()
    except ParsingError as exc:
        doc.status = Document.Status.ERROR
        doc.error_message = str(exc)[:2000]
        doc.save(update_fields=["status", "error_message", "updated_at"])
        logger.warning("document %s failed to parse: %s", document_id, exc)
        return doc.status
    except Exception as exc:
        doc.status = Document.Status.ERROR
        doc.error_message = str(exc)[:2000]
        doc.save(update_fields=["status", "error_message", "updated_at"])
        raise

    with transaction.atomic():
        DocumentChunk.objects.filter(document=doc).delete()
        DocumentChunk.objects.bulk_create(
            DocumentChunk(
                document=doc,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page,
                text=chunk.text,
                metadata={
                    **chunk.metadata,
                    "token_count": chunk.token_count,
                },
            )
            for chunk in chunks
        )

        doc.refresh_from_db()
        if doc.status != Document.Status.PROCESSING:
            logger.warning("document %s changed state mid-flight", document_id)
            return doc.status
        doc.status = Document.Status.READY if chunks else Document.Status.ERROR
        if not chunks:
            doc.error_message = "No extractable text found in the document."
        else:
            doc.error_message = ""
        doc.save(update_fields=["status", "error_message", "updated_at"])

    logger.info("document %s processed (%d chunks)", document_id, len(chunks))
    # Phase 6: after parsing succeeds, embed the chunks in a follow-up task.
    if chunks:
        embed_document.delay(document_id)
    return doc.status


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def embed_document(self, document_id: int) -> str:
    """Embed all chunks of a document with text-embedding-3-small."""
    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        logger.warning("embed_document: document %s vanished; skipping", document_id)
        return "missing"

    chunks = list(
        doc.chunks.filter(embedding__isnull=True).order_by("chunk_index")
    )
    if not chunks:
        return "already-embedded"

    try:
        vectors = embed_chunks_batch([c.text for c in chunks])
    except Exception as exc:
        self.retry(exc=exc, countdown=(2**self.request.retries) * 5)

    if len(vectors) != len(chunks):
        raise ValueError(
            f"embedding count mismatch (got {len(vectors)} want {len(chunks)}); "
            "refusing to write partial vectors"
        )

    with transaction.atomic():
        for chunk, vector in zip(chunks, vectors, strict=False):
            chunk.embedding = vector
        DocumentChunk.objects.bulk_update(chunks, ["embedding"])

    embedded = doc.chunks.filter(embedding__isnull=False).count()
    total = doc.chunks.count()
    logger.info("document %s embedded (%d/%d chunks)", document_id, embedded, total)
    return "embedded"
