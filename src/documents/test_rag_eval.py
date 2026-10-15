"""Phase 9: RAG retrieval evaluation (golden-question -> expected chunk).

Uses deterministic fake embeddings (no network) so retrieval quality can be
asserted as data, matching the roadmap's 'golden question set + hit@k' goal.
"""

import pytest

from documents.ai_engine import search_semantic
from documents.models import Document, DocumentChunk

pytestmark = pytest.mark.django_db


def _vector_for(text: str) -> list[float]:
    """Deterministic signature vector so semantically related topics cluster."""
    buckets = {
        "revenue": 0, "gelir": 0, "income": 0,
        "q3": 1, "q4": 1, "quarter": 1,
        "budget": 2, "bütçe": 2,
        "staff": 3, "personel": 3, "hire": 3,
    }
    v = [0.0] * 4 + [0.0] * (1536 - 4)
    for word, idx in buckets.items():
        if word in text.lower():
            v[idx] += 1.0
    norm = sum(abs(x) for x in v) or 1.0
    return [x / norm for x in v[:4]] + [0.0] * (1536 - 4)


@pytest.fixture
def fake_embeddings(monkeypatch):
    def fake_embed_texts(texts, **_kwargs):
        return [_vector_for(t) for t in texts]

    monkeypatch.setattr("documents.ai_engine.embed_texts", fake_embed_texts)
    return _vector_for


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        username="rg", email="rg@example.com", password="Pass123!"
    )


def _add_doc(owner, title, chunks):
    doc = Document.objects.create(
        owner=owner,
        title=title,
        original_filename=f"{title}.pdf",
        doc_type="pdf",
        status=Document.Status.READY,
    )
    return DocumentChunk.objects.bulk_create(
        [
            DocumentChunk(
                document=doc,
                chunk_index=i,
                page_number=i + 1,
                text=text,
                embedding=_vector_for(text),
            )
            for i, text in enumerate(chunks)
        ]
    )


def test_retrieval_finds_correct_chunk_for_golden_question(user, fake_embeddings):
    """hit@k: a revenue question surfaces the revenue chunk in the top-3."""
    _add_doc(user, "finans", [
        "Our Q3 revenue grew 20%.",
        "Hiring plans for next year.",
        "Budget allocation for R&D.",
        "Staff headcount as of Q3.",
    ])

    results = search_semantic(user, "What is the Q3 revenue?", top_k=3)

    assert results, "expected at least one retrieved chunk"
    # The question shares the most topic buckets with chunk 0 (revenue).
    assert results[0].chunk_index == 0


def test_retrieval_is_permission_scoped(user):
    """A user must never see another user's private document chunks."""
    from conftest import make_user

    owner = make_user(username="rgo", email="rgo@example.com")
    _add_doc(owner, "gizli", ["private secret payload"])

    outsider = make_user(username="rsv", email="rsv@example.com")
    results = search_semantic(outsider, "secret", top_k=8)

    assert results == [], "must not surface other users' private chunks"
