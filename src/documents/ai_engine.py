"""Phase 6: embeddings and pgvector semantic search.

`embed_chunks_batch()` calls the OpenAI embeddings API in batches (so we
can rate-limit safely); `search_semantic()` embeds a query and runs a
cosine (<=>) top-k query against `DocumentChunk.embedding`. Every search is
scoped to the requesting user's permissions (owner is_public or admin).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable

from .models import Document, DocumentChunk

logger = logging.getLogger(__name__)

BATCH_SIZE = 64
MAX_RETRIES = 5
RETRY_BASE_DELAY = 0.5

EMBEDDING_MODEL = "text-embedding-3-small"


def _client():
    """Lazy OpenAI client; key comes from the OPENAI_API_KEY env var."""
    from openai import OpenAI

    return OpenAI()


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    """Embed a sequence of texts (single API call, caller batches the list)."""
    client = _client()
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=list(texts),
    )
    data = sorted(response.data, key=lambda d: d.index)
    return [d.embedding for d in data]


def embed_chunks_batch(texts: Iterable[str]) -> list[list[float]]:
    """
    Embed texts in batches of 64 with exponential backoff on 429/rate-limit.

    Returns one embedding per input text in the same order.
    """
    texts = list(texts)
    result: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        for attempt in range(MAX_RETRIES):
            try:
                result.extend(embed_texts(batch))
                break
            except Exception as exc:  # transient API/rate-limit errors
                if attempt == MAX_RETRIES - 1:
                    raise
                delay = RETRY_BASE_DELAY * (2**attempt)
                logger.warning("embedding batch failed (%s); retrying in %.1fs", exc, delay)
                time.sleep(delay)
    return result


def _visible_chunk_filter(user):
    """Return a Q() scoping DocumentChunk queries to documents the user may see."""
    from django.db.models import Q

    if getattr(user, "is_superuser", False) or getattr(user, "role", None) == "admin":
        return Q()
    return Q(document__owner_id=user.pk) | Q(document__is_public=True)


def _visible_document_filter(user):
    """Return a Q() scoping Document queries to documents the user may see."""
    from django.db.models import Q

    if getattr(user, "is_superuser", False) or getattr(user, "role", None) == "admin":
        return Q()
    return Q(owner_id=user.pk) | Q(is_public=True)


def search_semantic(user, query: str, *, top_k: int = 8) -> list:
    """
    Return top-k DocumentChunk objects semantically similar to the query,
    scoped to the user's permissions. Returns [] when the query is empty.
    """
    if not query or not query.strip():
        return []

    [query_embedding] = embed_texts([query.strip()])

    from pgvector.django import CosineDistance

    qs = (
        DocumentChunk.objects.filter(_visible_chunk_filter(user))
        .exclude(embedding__isnull=True)
        .order_by(CosineDistance("embedding", query_embedding))
        .select_related("document")[:top_k]
    )
    return list(qs)


def get_document_chunks(user, document_id: int, page: int | None = None) -> list:
    """Return chunks of a specific document the user can access."""
    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        return []
    if not (doc.owner_id == user.pk or doc.is_public or user.is_superuser):
        return []
    qs = doc.chunks.order_by("chunk_index")
    if page is not None:
        qs = qs.filter(page_number=page)
    return list(qs)


def list_documents(user) -> list:
    """Return documents the user can see, newest first."""
    return list(
        Document.objects.filter(_visible_document_filter(user)).order_by("-created_at")
    )


def get_document_metadata(user, document_id: int) -> dict | None:
    """Return basic metadata of a document the user can access."""
    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        return None
    if not (doc.owner_id == user.pk or doc.is_public or user.is_superuser):
        return None
    return {
        "id": doc.pk,
        "title": doc.title,
        "doc_type": doc.doc_type,
        "original_filename": doc.original_filename,
        "size_bytes": doc.size_bytes,
        "is_public": doc.is_public,
        "created_at": doc.created_at,
    }
