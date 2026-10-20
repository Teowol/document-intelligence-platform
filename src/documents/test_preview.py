"""Original-file access, safe rendering and bounded spreadsheet previews."""

import io

import pytest
from django.urls import reverse
from openpyxl import Workbook

from accounts.models import CustomUser
from conftest import MINIMAL_PDF, make_document, make_user
from documents.preview import TABLE_COLUMNS, TABLE_ROWS, TEXT_BYTES, build_preview

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("route", ["detail", "file"])
@pytest.mark.parametrize("visitor", ["owner", "admin", "other", "public", "anonymous"])
def test_original_access_matches_document_permissions(client, route, visitor):
    owner = make_user("owner")
    doc = make_document(owner, is_public=visitor == "public")
    if visitor == "owner":
        client.force_login(owner)
    elif visitor == "admin":
        client.force_login(make_user("admin", role=CustomUser.Roles.ADMIN))
    elif visitor != "anonymous":
        client.force_login(make_user("other"))
    response = client.get(reverse(f"documents:{route}", args=[doc.pk]))
    assert response.status_code == {"other": 403, "anonymous": 302}.get(visitor, 200)
    response.close()


@pytest.mark.parametrize("download", [False, True])
def test_pdf_inline_and_download_headers(client, download):
    owner = make_user()
    doc = make_document(owner, original_filename="özgün belge.pdf")
    client.force_login(owner)
    url = reverse("documents:file", args=[doc.pk])
    response = client.get(url, {"download": "1"} if download else {})
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith("attachment;" if download else "inline;")
    assert response["X-Frame-Options"] == "SAMEORIGIN"
    assert response["Cache-Control"] == "private, no-store"
    assert b"".join(response.streaming_content) == MINIMAL_PDF


@pytest.mark.parametrize("doc_type", ["txt", "md"])
def test_original_text_is_escaped_and_available_before_processing(client, doc_type):
    owner = make_user()
    doc = make_document(
        owner, pdf_bytes=b'<script>alert("xss")</script>\nOriginal text beyond chunks',
        doc_type=doc_type, status="uploaded",
    )
    client.force_login(owner)
    response = client.get(reverse("documents:detail", args=[doc.pk]))
    html = response.content.decode()
    assert '&lt;script&gt;' in html
    assert '<script>alert(' not in html
    assert 'Original text beyond chunks' in html
    assert 'http-equiv="refresh"' not in html
    assert 'Refresh status' in html
    assert response.context["preview"]["kind"] == "text"


def test_text_preview_is_bounded():
    doc = make_document(make_user(), pdf_bytes=b"x" * (TEXT_BYTES + 10), doc_type="txt")
    preview = build_preview(doc)
    assert preview["truncated"]
    assert len(preview["text"]) == TEXT_BYTES


def test_csv_delimiters_and_limits():
    data = (";".join(f"cell {i}" for i in range(TABLE_COLUMNS + 1)) + "\n") * (TABLE_ROWS + 1)
    doc = make_document(make_user(), pdf_bytes=data.encode(), doc_type="csv")
    preview = build_preview(doc)
    assert preview["truncated"]
    assert len(preview["rows"]) == TABLE_ROWS
    assert len(preview["rows"][0]) == TABLE_COLUMNS
    assert preview["rows"][0][1] == "cell 1"


def test_excel_sheet_selection_and_literal_formulas():
    workbook = Workbook()
    workbook.active.title = "First"
    workbook.active.append(["Name", "Value"])
    workbook.active.append(["Budget", 123])
    workbook.create_sheet("Second").append(["Other sheet", "=1+1"])
    content = io.BytesIO()
    workbook.save(content)
    workbook.close()
    doc = make_document(make_user(), pdf_bytes=content.getvalue(), doc_type="xlsx")
    preview = build_preview(doc)
    assert preview["rows"][1] == ["Budget", "123"]
    assert not preview["truncated"]
    assert preview["sheets"] == ["First", "Second"]
    assert build_preview(doc, "Second")["rows"] == [["Other sheet", ""]]
    assert build_preview(doc, "missing")["selected_sheet"] == "First"


def test_missing_original_returns_404_without_breaking_detail(client):
    owner = make_user()
    doc = make_document(owner, doc_type="txt")
    doc.file.storage.delete(doc.file.name)
    client.force_login(owner)
    response = client.get(reverse("documents:detail", args=[doc.pk]))
    assert response.status_code == 200
    assert response.context["preview"]["kind"] == "unavailable"
    assert client.get(reverse("documents:file", args=[doc.pk])).status_code == 404


def test_non_pdf_originals_are_attachments_with_safe_content_type(client):
    owner = make_user()
    doc = make_document(owner, pdf_bytes=b"<script>alert(1)</script>", doc_type="md")
    client.force_login(owner)
    response = client.get(reverse("documents:file", args=[doc.pk]))
    assert response["Content-Disposition"].startswith("attachment;")
    assert response["Content-Type"].startswith("text/plain")
    response.close()
