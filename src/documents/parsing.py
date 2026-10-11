"""Phase 5: parsing, normalization and chunking.

Each file type has its own extractor that yields raw "sections" -- a page
of a PDF, a sheet/row-block of a spreadsheet, a heading-delimited block of
a Markdown file, etc. Every section is normalized the same way and fed to
a shared recursive splitter so `DocumentChunk` rows stay consistent no
matter the source format.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field

import openpyxl
import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter
from PyPDF2 import PdfReader

CHUNK_SIZE = 700
CHUNK_OVERLAP = 70  # ~10% of CHUNK_SIZE
TOKEN_ENCODING = "cl100k_base"

# Row-based formats (csv/xlsx): group this many data rows per section so a
# single chunk still fits comfortably under CHUNK_SIZE once rendered as text.
ROWS_PER_SECTION = 20


class ParsingError(Exception):
    """Raised when a document's content cannot be parsed."""


@dataclass
class Section:
    text: str
    page: int | None = None
    heading: str = ""


@dataclass
class Chunk:
    text: str
    chunk_index: int
    page: int | None
    heading: str
    token_count: int
    metadata: dict = field(default_factory=dict)


def normalize_text(text: str) -> str:
    """Unicode-normalize, collapse whitespace, trim blank-line runs."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def count_tokens(text: str) -> int:
    encoding = tiktoken.get_encoding(TOKEN_ENCODING)
    return len(encoding.encode(text))


def _splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def extract_sections(fileobj, doc_type: str) -> list[Section]:
    """Dispatch to the right extractor and return normalized sections."""
    extractors = {
        "pdf": _extract_pdf,
        "xlsx": _extract_xlsx,
        "csv": _extract_csv,
        "md": _extract_markdown,
        "txt": _extract_text,
    }
    extractor = extractors.get(doc_type)
    if extractor is None:
        raise ParsingError(f"Unsupported doc_type: {doc_type!r}")

    fileobj.seek(0)
    try:
        sections = extractor(fileobj)
    except ParsingError:
        raise
    except Exception as exc:  # pragma: no cover - defensive wrapper
        raise ParsingError(f"Failed to parse {doc_type} file: {exc}") from exc

    return [s for s in sections if s.text]


def _extract_pdf(fileobj) -> list[Section]:
    reader = PdfReader(fileobj)
    sections = []
    for index, page in enumerate(reader.pages, start=1):
        raw = page.extract_text() or ""
        text = normalize_text(raw)
        if text:
            sections.append(Section(text=text, page=index))
    return sections


def _extract_xlsx(fileobj) -> list[Section]:
    workbook = openpyxl.load_workbook(fileobj, read_only=True, data_only=True)
    sections = []
    for sheet in workbook.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            continue
        header, *data_rows = rows
        header_line = ", ".join(str(c) for c in header if c is not None)

        for start in range(0, len(data_rows), ROWS_PER_SECTION):
            block = data_rows[start : start + ROWS_PER_SECTION]
            lines = [header_line] if header_line else []
            for row in block:
                lines.append(", ".join("" if c is None else str(c) for c in row))
            text = normalize_text("\n".join(lines))
            if text:
                sections.append(Section(text=text, heading=sheet.title))
    return sections


def _extract_csv(fileobj) -> list[Section]:
    raw_bytes = fileobj.read()
    text_stream = io.StringIO(raw_bytes.decode("utf-8", errors="replace"))
    reader = csv.reader(text_stream)
    rows = list(reader)
    if not rows:
        return []

    header, *data_rows = rows
    header_line = ", ".join(header)
    sections = []
    for start in range(0, len(data_rows), ROWS_PER_SECTION):
        block = data_rows[start : start + ROWS_PER_SECTION]
        lines = [header_line] + [", ".join(row) for row in block]
        text = normalize_text("\n".join(lines))
        if text:
            sections.append(Section(text=text))
    return sections


def _extract_text(fileobj) -> list[Section]:
    raw = fileobj.read()
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    text = normalize_text(text)
    return [Section(text=text)] if text else []


_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def _extract_markdown(fileobj) -> list[Section]:
    raw = fileobj.read()
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw

    headings = list(_MD_HEADING_RE.finditer(text))
    if not headings:
        normalized = normalize_text(text)
        return [Section(text=normalized)] if normalized else []

    sections = []
    for i, match in enumerate(headings):
        start = match.start()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        block = normalize_text(text[start:end])
        if block:
            sections.append(Section(text=block, heading=match.group(2).strip()))
    return sections


def chunk_sections(sections: list[Section]) -> list[Chunk]:
    """Split normalized sections into overlapping, metadata-tagged chunks."""
    splitter = _splitter()
    chunks: list[Chunk] = []
    index = 0
    for section in sections:
        pieces = splitter.split_text(section.text) or [section.text]
        for piece in pieces:
            chunks.append(
                Chunk(
                    text=piece,
                    chunk_index=index,
                    page=section.page,
                    heading=section.heading,
                    token_count=count_tokens(piece),
                    metadata={
                        "page": section.page,
                        "section_heading": section.heading,
                    },
                )
            )
            index += 1
    return chunks


def parse_and_chunk(fileobj, doc_type: str) -> list[Chunk]:
    """Full Phase 5 pipeline: extract -> normalize -> chunk."""
    sections = extract_sections(fileobj, doc_type)
    return chunk_sections(sections)
