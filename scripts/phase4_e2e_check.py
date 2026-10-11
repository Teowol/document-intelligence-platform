"""Phase 4/5 live E2E check: dispatch process_document to the real Celery worker.

Run with the worker up (celery -A config worker --pool=solo):
    cd src && ../venv/Scripts/python ../scripts/phase4_e2e_check.py

Prints status transitions observed in the DB, confirms real chunks were
written by the Phase 5 parser, then cleans up.
"""

import os
import sys
import time
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
django.setup()

from django.core.files.base import ContentFile  # noqa: E402
from fpdf import FPDF  # noqa: E402

from documents.models import Document  # noqa: E402
from documents.tasks import process_document  # noqa: E402


def _make_pdf_bytes() -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, "Phase 5 end-to-end check: real text for the parser to chunk.")
    return bytes(pdf.output())


MINIMAL_PDF = _make_pdf_bytes()


def main():
    from accounts.models import CustomUser

    user, _ = CustomUser.objects.get_or_create(
        email="admin@test.local",
        defaults={"username": "admin", "is_superuser": True, "is_staff": True},
    )

    doc = Document(owner=user, title="Phase4 E2E", original_filename="e2e.pdf",
                   doc_type="pdf")
    doc.file.save("e2e.pdf", ContentFile(MINIMAL_PDF), save=True)
    print(f"created doc #{doc.pk} status={doc.status}")

    async_result = process_document.delay(doc.pk)
    print(f"task dispatched: {async_result.task_id} (real Redis broker)")

    seen = {doc.status}
    for _ in range(40):
        time.sleep(0.25)
        doc.refresh_from_db()
        seen.add(doc.status)
        if doc.status in (Document.Status.READY, Document.Status.ERROR):
            break

    print("observed statuses:", " -> ".join(sorted(seen)))
    doc.refresh_from_db()
    print(f"final: status={doc.status} error={doc.error_message!r}")

    chunks = list(doc.chunks.order_by("chunk_index"))
    print(f"chunks written: {len(chunks)}")
    if chunks:
        print(f"  chunk[0].page={chunks[0].page_number} text={chunks[0].text[:80]!r}")

    # cleanup
    doc.file.delete(save=False)
    doc.delete()
    print("cleaned up")
    return 0 if doc.status == Document.Status.READY and chunks else 1


if __name__ == "__main__":
    raise SystemExit(main())
