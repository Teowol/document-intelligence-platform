"""Phase 6 live E2E check: embedding + semantic search through the real worker.

This verifies the FULL pipeline end-to-end: upload -> process_document
(parse+chunk) -> embed_document (embeddings) -> search_semantic.

REQUIRES a valid OPENAI_API_KEY in .env. Run with the worker up:
    cd src && ../venv/Scripts/python ../scripts/phase6_e2e_check.py

Prints chunk + embedding counts and a semantic search result, then cleans up.
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

from documents.ai_engine import search_semantic  # noqa: E402
from documents.models import Document  # noqa: E402
from documents.tasks import process_document  # noqa: E402


def _make_pdf_bytes() -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, "Quarterly budget projections for the engineering team.")
    return bytes(pdf.output())


def _wait_status(doc, target, timeout=60):
    seen = {doc.status}
    elapsed = 0.0
    while elapsed < timeout:
        doc.refresh_from_db()
        seen.add(doc.status)
        if doc.status == target:
            return seen
        time.sleep(0.4)
        elapsed += 0.4
    return seen


def main():
    from accounts.models import CustomUser

    key_missing = not os.environ.get("OPENAI_API_KEY")
    if key_missing:
        print("WARNING: OPENAI_API_KEY is empty; embeddings will fail (401).")
        print("Set a valid key in .env and re-run for a real embedding check.")

    user, _ = CustomUser.objects.get_or_create(
        email="admin@test.local",
        defaults={"username": "admin", "is_superuser": True, "is_staff": True},
    )

    doc = Document(owner=user, title="Phase6 E2E", original_filename="e2e-budget.pdf",
                   doc_type="pdf")
    doc.file.save("e2e-budget.pdf", ContentFile(_make_pdf_bytes()), save=True)
    print(f"created doc #{doc.pk} status={doc.status}")

    print("dispatching process_document (which chains embed_document)...")
    process_document.delay(doc.pk)

    ready_seen = _wait_status(doc, Document.Status.READY)
    print("process statuses:", " -> ".join(sorted(ready_seen)))

    # Wait for embeddings to appear (embed_document runs after parsing).
    embedded = 0
    for _ in range(150):  # up to ~75s
        doc.refresh_from_db()
        embedded = doc.chunks.filter(embedding__isnull=False).count()
        if embedded:
            break
        time.sleep(0.5)

    total = doc.chunks.count()
    print(f"chunks={total} embedded={embedded}")

    if embedded:
        results = search_semantic(user, "budget projections")
        print(f"semantic search returned {len(results)} result(s)")
        if results:
            r = results[0]
            print(f"  top result: {r.document.original_filename!r} "
                  f"score-ish page={r.page_number} text={r.text[:60]!r}")

    # cleanup
    doc.file.delete(save=False)
    doc.delete()
    print("cleaned up")
    return 0 if embedded and total else 1


if __name__ == "__main__":
    raise SystemExit(main())
