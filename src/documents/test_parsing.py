"""Phase 5 tests: each supported file type parses into tracked chunks."""

import io

import openpyxl
import pytest
from fpdf import FPDF

from documents.parsing import (
    ParsingError,
    chunk_sections,
    count_tokens,
    extract_sections,
    normalize_text,
    parse_and_chunk,
)


def _pdf_bytes(lines: list[str]) -> bytes:
    pdf = FPDF()
    for line in lines:
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.multi_cell(0, 10, line)
    return bytes(pdf.output())


def _xlsx_bytes(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_normalize_text_collapses_whitespace_and_unicode():
    raw = "Café   test\r\n\r\n\r\nmore\u00a0text"
    result = normalize_text(raw)
    assert "\r" not in result
    assert "   " not in result
    assert "\n\n\n" not in result


def test_count_tokens_nonzero():
    assert count_tokens("hello world") > 0


def test_pdf_extraction_tracks_page_numbers():
    data = _pdf_bytes(["Page one content.", "Page two content."])
    sections = extract_sections(io.BytesIO(data), "pdf")
    assert len(sections) == 2
    assert sections[0].page == 1
    assert "Page one" in sections[0].text
    assert sections[1].page == 2


def test_xlsx_extraction_includes_header_and_rows():
    data = _xlsx_bytes(
        [["name", "age"], ["Ada", 36], ["Alan", 41]]
    )
    sections = extract_sections(io.BytesIO(data), "xlsx")
    assert len(sections) == 1
    assert "name" in sections[0].text
    assert "Ada" in sections[0].text
    assert sections[0].heading == "Sheet1"


def test_csv_extraction_preserves_header():
    data = b"name,age\nAda,36\nAlan,41\n"
    sections = extract_sections(io.BytesIO(data), "csv")
    assert len(sections) == 1
    assert sections[0].text.startswith("name, age")
    assert "Ada" in sections[0].text


def test_txt_extraction_returns_single_section():
    data = b"This is a plain text file with some content.\n"
    sections = extract_sections(io.BytesIO(data), "txt")
    assert len(sections) == 1
    assert "plain text file" in sections[0].text


def test_markdown_extraction_splits_on_headings():
    data = (
        b"# Intro\nSome intro text.\n\n"
        b"## Details\nMore detailed text here.\n"
    )
    sections = extract_sections(io.BytesIO(data), "md")
    assert len(sections) == 2
    assert sections[0].heading == "Intro"
    assert sections[1].heading == "Details"


def test_unsupported_doc_type_raises():
    with pytest.raises(ParsingError):
        extract_sections(io.BytesIO(b"x"), "exe")


def test_chunk_sections_respects_overlap_and_index():
    long_text = ("This is a sentence that repeats. " * 60).strip()
    from documents.parsing import Section

    sections = [Section(text=long_text, page=1)]
    chunks = chunk_sections(sections)
    assert len(chunks) > 1
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks)))
    for chunk in chunks:
        assert chunk.metadata["page"] == 1
        assert chunk.token_count > 0


def test_parse_and_chunk_end_to_end_pdf():
    data = _pdf_bytes(["End to end parsing test content for phase five."])
    chunks = parse_and_chunk(io.BytesIO(data), "pdf")
    assert len(chunks) >= 1
    assert "parsing test" in chunks[0].text
