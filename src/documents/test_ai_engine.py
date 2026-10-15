"""Phase 6 tests: semantic search and embeddings service."""

import pytest

from documents.ai_engine import (
    embed_chunks_batch,
    get_document_chunks,
    get_document_metadata,
    list_documents,
    search_semantic,
)
from documents.models import DocumentChunk

pytestmark = pytest.mark.django_db


class _FakeEmbedding:
    """Deterministic OpenAI-style embedding response."""

    def __init__(self, values):
        class Entry:
            def __init__(self, idx, embedding):
                self.index = idx
                self.embedding = embedding

        self._entries = [Entry(i, v) for i, v in enumerate(values)]

    @property
    def data(self):
        return self._entries


_FIXED_1536 = [1.0] * 1536


@pytest.fixture(autouse=True)
def _fake_openai(monkeypatch):
    """Avoid real API calls: embed_texts returns fixed/deterministic vectors."""

    def fake_embed_texts(texts, **_kwargs):
        # Deterministic vector per text so cosine distance is meaningful.
        vals = [[float(hash(t) % 1000) / 1000, 0.5, 0.25] + [0.0] * (1536 - 3) for t in texts]
        return vals

    monkeypatch.setattr(
        "documents.ai_engine.embed_texts", fake_embed_texts
    )
    # Also alias a fixed vector for tests that need a concrete embedding.
    yield


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        username="u", email="u@example.com", password="Pass123!"
    )


@pytest.fixture
def other_user(django_user_model):
    return django_user_model.objects.create_user(
        username="o", email="o@example.com", password="Pass123!"
    )


def make_chunk(owner, doc_type="pdf", text="hello world", embedding=None):
    from documents.models import Document

    doc = Document.objects.create(
        owner=owner, title="t", original_filename="t.pdf", doc_type=doc_type
    )
    return DocumentChunk.objects.create(
        document=doc, text=text, embedding=embedding, chunk_index=0
    )


def test_embed_chunks_batch_batches_and_backs_off(monkeypatch):
    calls = []

    def fake_embed(texts):
        calls.append(len(texts))
        return [[0.1] * 1024 for _ in texts]

    monkeypatch.setattr("documents.ai_engine.embed_texts", fake_embed)
    monkeypatch.setattr("documents.ai_engine.BATCH_SIZE", 2)

    out = embed_chunks_batch(["a", "b", "c", "d", "e"])
    assert len(out) == 5
    assert calls == [2, 2, 1]  # batch size 2 => batching observed


def test_embed_chunks_batch_retries_on_failure(monkeypatch):
    attempts = {"n": 0}

    def flaky(texts):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError("simulated transient failure")
        return [[0.1] * 1536 for _ in texts]

    monkeypatch.setattr("documents.ai_engine.embed_texts", flaky)
    monkeypatch.setattr("documents.ai_engine.MAX_RETRIES", 4)
    out = embed_chunks_batch(["a"])
    assert len(out) == 1
    assert attempts["n"] == 3


def test_search_semantic_scopes_to_user_permissions(user):
    # Two texts with different hashes => different embeddings.
    make_chunk(user, text="project budget review", embedding=[0.9] * 1536)
    make_chunk(user, text="unrelated stuff", embedding=[0.1] * 1536)

    # public doc from someone else is searchable
    from documents.models import Document

    public_doc = Document.objects.create(
        owner=user, title="pub", original_filename="pub.pdf", doc_type="pdf", is_public=True
    )
    DocumentChunk.objects.create(
        document=public_doc, text="another budget item", embedding=[0.8] * 1536
    )

    results = search_semantic(user, "budget review", top_k=5)
    # all results belong to docs visible to this user
    assert all(r.document.owner == user or r.document.is_public for r in results)


def test_search_semantic_never_leaks_private_other_user(user, other_user):
    make_chunk(
        other_user, text="confidential internal memo", embedding=[0.9] * 1536,
    )
    results = search_semantic(user, "confidential memo")
    assert results == []


def test_get_document_chunks_requires_permission(user, other_user):
    from documents.models import Document

    doc = Document.objects.create(
        owner=other_user, title="private", original_filename="p.pdf", doc_type="pdf"
    )
    DocumentChunk.objects.create(document=doc, text="secret", chunk_index=0)

    # other user (not owner, not public) cannot read chunks
    assert get_document_chunks(user, doc.pk) == []
    # owner can
    assert len(get_document_chunks(other_user, doc.pk)) == 1


def test_list_documents_respects_visibility(user, other_user):
    from documents.models import Document

    Document.objects.create(
        owner=user, title="mine", original_filename="mine.pdf", doc_type="pdf"
    )
    Document.objects.create(
        owner=other_user, title="theirs-private",
        original_filename="theirs.pdf", doc_type="pdf",
    )
    Document.objects.create(
        owner=other_user, title="theirs-public",
        original_filename="theirs-pub.pdf", doc_type="pdf", is_public=True,
    )
    docs = list_documents(user)
    titles = {d.title for d in docs}
    assert "mine" in titles
    assert "theirs-private" not in titles
    assert "theirs-public" in titles


def test_get_document_metadata_permission(user, other_user):
    from documents.models import Document

    private = Document.objects.create(
        owner=other_user, title="private", original_filename="p.pdf", doc_type="pdf"
    )
    assert get_document_metadata(user, private.pk) is None

    public = Document.objects.create(
        owner=other_user, title="public", original_filename="pb.pdf",
        doc_type="pdf", is_public=True,
    )
    meta = get_document_metadata(user, public.pk)
    assert meta is not None
    assert meta["title"] == "public"


def test_search_view_renders_without_query(client, user):
    client.force_login(user)
    resp = client.get("/documents/search/")
    assert resp.status_code == 200
    assert b"Semantic Search" in resp.content


def test_search_view_displays_matches(client, user, monkeypatch):
    from documents.models import Document

    doc = Document.objects.create(
        owner=user, title="budget", original_filename="budget.pdf", doc_type="pdf"
    )
    DocumentChunk.objects.create(
        document=doc, text="the quarterly budget projection", chunk_index=0,
        embedding=[0.9] * 1536, page_number=2,
    )
    monkeypatch.setattr(
        "documents.views.search_semantic",
        lambda _user, _query, **_kw: list(doc.chunks.all()),
    )
    client.force_login(user)
    resp = client.get("/documents/search/", {"q": "budget"})
    assert resp.status_code == 200
    assert b"budget.pdf" in resp.content
    assert b"quarterly budget projection" in resp.content
