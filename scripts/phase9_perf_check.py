"""Phase 9 performance check: measure parsing + semantic search latency.

Small service-level latency harness (no HTTP). Prints millisecond timings so
you can note a before/after baseline and spot regressions. Requires Django
imports only, runs against the configured DB.

Usage (from src/):
    python ../scripts/phase9_perf_check.py
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
from documents.parsing import parse_and_chunk  # noqa: E402


def _pdf_bytes() -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    for _ in range(20):
        pdf.multi_cell(w=180, h=10, text="A benchmark line for phase nine latency checks.")
    return bytes(pdf.output())


def measure(fn, *args, label, rounds=10):
    times = []
    for _ in range(rounds):
        start = time.perf_counter()
        fn(*args)
        times.append((time.perf_counter() - start) * 1000)
    avg = sum(times) / len(times)
    print(f"{label:32s} avg={avg:8.1f} ms  (min={min(times):.1f}, max={max(times):.1f})")
    return avg


if __name__ == "__main__":
    pdf = _pdf_bytes()

    def _parse():
        parse_and_chunk(__import__("io").BytesIO(pdf), "pdf")

    count = 0

    def _count_chunks():
        global count
        count = Document.objects.filter(status=Document.Status.READY).count()

    print("Phase 9 latency baseline (10 warm runs each)\n")
    measure(_parse, label="parse+chunk (20-page PDF)")
    measure(_count_chunks, label="count ready docs (DB)")
    print(f"\nready docs in DB: {count}")
