"""Shared pytest fixtures & factories (Phase 9).

Centralizes user/document factories so every test module stops re-declaring
them. Re-usable Copyright/add fixtures here; import factories explicitly.
"""

import pytest
from django.core.files.base import ContentFile

from accounts.models import CustomUser
from documents.models import Document, DocumentChunk

MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>"


@pytest.fixture(autouse=True)
def _media_root(settings, tmp_path):
    """Point MEDIA_ROOT at a temp dir for every test module by default."""
    settings.MEDIA_ROOT = str(tmp_path)
    settings.MAX_UPLOAD_SIZE = 25 * 1024 * 1024


def make_user(username="u", email=None, role=CustomUser.Roles.VIEWER, **kwargs):
    """Create a user with sane defaults; email auto-derived from username."""
    email = email or f"{username}@example.com"
    return CustomUser.objects.create_user(
        username=username,
        email=email,
        password="Pass123!",
        role=role,
        **kwargs,
    )


def make_document(owner, pdf_bytes=MINIMAL_PDF, **overrides):
    """Create a Document row directly (bypasses the upload HTTP flow)."""
    doc = Document(
        owner=owner,
        title=overrides.pop("title", "t"),
        original_filename=overrides.pop("original_filename", "t.pdf"),
        doc_type=overrides.pop("doc_type", Document.DocType.PDF),
        is_public=overrides.pop("is_public", False),
        status=overrides.pop("status", Document.Status.READY),
        **overrides,
    )
    doc.file.save(
        overrides.pop("save_name", "t.pdf"), ContentFile(pdf_bytes), save=True
    )
    doc.save()
    return doc


def make_chunks(doc, count=3):
    """Populate a handful of chunks for a document."""
    return DocumentChunk.objects.bulk_create(
        DocumentChunk(
            document=doc,
            chunk_index=i,
            page_number=i + 1,
            text=f"chunk {i} of {doc.title}",
        )
        for i in range(count)
    )
