"""Background tasks for document processing.

Phase 5: real parsing + chunking replaces the Phase 4 placeholder.
The status machine stays production-shaped:

    uploaded -> processing -> ready
                        \\-----> error (parsing failure or unexpected crash)
"""

import logging

from celery import shared_task
from django.db import transaction

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
    doc.save(update_fields=["status", "updated_at"])

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
    return doc.status
