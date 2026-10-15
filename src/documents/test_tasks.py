"""Phase 4/5 tests: Celery task drives parsing + the document status machine."""

import pytest
from django.core.files.base import ContentFile
from fpdf import FPDF

from accounts.models import CustomUser
from documents.models import Document, DocumentChunk
from documents.tasks import process_document

pytestmark = pytest.mark.django_db


def _make_pdf_bytes(text: str = "Hello world, this is a test document.") -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, text)
    return bytes(pdf.output())


MINIMAL_PDF = _make_pdf_bytes()


@pytest.fixture(autouse=True)
def _eager(settings, tmp_path, monkeypatch):
    """Run tasks synchronously and store results in memory during tests."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    settings.MEDIA_ROOT = str(tmp_path)
    # Phase 6: the parsing task chains an embedding task; tests focus on the
    # parse/chunk status machine, so keep embeds from hitting the OpenAI API.
    monkeypatch.setattr(
        "documents.tasks.embed_document.delay",
        lambda *a, **kw: None,
    )


@pytest.fixture
def user():
    return CustomUser.objects.create_user(
        username="u", email="u@example.com", password="Pass123!"
    )


def make_doc(owner):
    doc = Document(
        owner=owner, title="t", original_filename="t.pdf", doc_type="pdf"
    )
    doc.file.save("t.pdf", ContentFile(MINIMAL_PDF), save=True)
    return doc


def test_task_moves_uploaded_to_ready(user):
    doc = make_doc(user)
    assert doc.status == Document.Status.UPLOADED

    result = process_document.delay(doc.pk)

    assert result.get() == Document.Status.READY
    doc.refresh_from_db()
    assert doc.status == Document.Status.READY
    assert doc.error_message == ""

    chunks = list(doc.chunks.order_by("chunk_index"))
    assert len(chunks) >= 1
    assert "Hello world" in chunks[0].text
    assert chunks[0].page_number == 1
    assert chunks[0].metadata["token_count"] > 0


def test_task_reprocessing_replaces_old_chunks(user):
    doc = make_doc(user)
    process_document.delay(doc.pk).get()
    first_chunk_ids = list(doc.chunks.values_list("id", flat=True))

    doc.status = Document.Status.UPLOADED
    doc.save(update_fields=["status"])
    process_document.delay(doc.pk).get()

    second_chunk_ids = list(doc.chunks.values_list("id", flat=True))
    assert DocumentChunk.objects.filter(document=doc).count() == len(second_chunk_ids)
    assert set(first_chunk_ids).isdisjoint(second_chunk_ids)


def test_task_marks_error_on_unparseable_content(user):
    doc = Document(
        owner=user, title="bad", original_filename="bad.pdf", doc_type="pdf"
    )
    doc.file.save("bad.pdf", ContentFile(b"not a real pdf"), save=True)

    result = process_document.delay(doc.pk)

    assert result.get() == Document.Status.ERROR
    doc.refresh_from_db()
    assert doc.status == Document.Status.ERROR
    assert doc.error_message
    assert doc.chunks.count() == 0


def test_task_marks_error_when_missing(user, settings, monkeypatch):
    """A vanished document is reported, not crash-looped."""
    result = process_document.delay(99999)
    assert result.get() == "missing"


def test_uploaded_doc_transitions_via_helper(user):
    doc = make_doc(user)
    doc.status = Document.Status.PROCESSING
    doc.save(update_fields=["status"])
    process_document.delay(doc.pk).get()
    doc.refresh_from_db()
    assert doc.status == Document.Status.READY
