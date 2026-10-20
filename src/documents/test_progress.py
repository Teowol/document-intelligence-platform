from unittest.mock import Mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from conftest import MINIMAL_PDF, make_chunks, make_document, make_user
from documents.models import Document

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(client, monkeypatch):
    user = make_user()
    client.force_login(user)
    monkeypatch.setattr("documents.views.process_document.delay", Mock())
    return user


def test_json_upload_returns_document_url_and_preserves_notification(client, owner):
    response = client.post(reverse("documents:upload"), {
        "title": "Upload", "file": SimpleUploadedFile("document.pdf", MINIMAL_PDF),
    }, HTTP_ACCEPT="application/json")
    assert response.status_code == 201
    document = Document.objects.get()
    assert response.json()["url"] == reverse("documents:detail", args=[document.pk])
    page = client.get(response.json()["url"]).content.decode()
    assert 'class="notification-stack"' in page
    assert 'data-level="success"' in page
    assert 'notification-countdown' in page
    assert 'alert-dismissible' not in page
    assert 'data-notification ' not in client.get(response.json()["url"]).content.decode()


def test_json_upload_validation_errors_are_localized(client, owner):
    client.cookies["django_language"] = "tr"
    response = client.post(reverse("documents:upload"), {"title": "Missing file"}, HTTP_ACCEPT="application/json")
    assert response.status_code == 400
    assert response.json()["errors"][0]["label"] == "Dosya"
    assert not Document.objects.exists()


def test_upload_without_javascript_still_redirects(client, owner):
    response = client.post(reverse("documents:upload"), {
        "title": "Upload", "file": SimpleUploadedFile("document.pdf", MINIMAL_PDF),
    })
    assert response.status_code == 302
    assert Document.objects.count() == 1


def test_invalid_file_is_rejected_for_progress_upload(client, owner):
    response = client.post(reverse("documents:upload"), {
        "title": "Fake", "file": SimpleUploadedFile("fake.pdf", b"MZ fake executable"),
    }, HTTP_ACCEPT="application/json")
    assert response.status_code == 400
    assert response.json()["errors"][0]["field"] == "file"
    assert not Document.objects.exists()


@pytest.mark.parametrize("status, expected", [("uploaded", 1), ("processing", 2), ("error", 0)])
def test_processing_status_uses_real_document_state(client, owner, status, expected):
    document = make_document(owner, status=status)
    response = client.get(reverse("documents:status", args=[document.pk]))
    assert response.status_code == 200
    assert response.json()["stage"] == expected
    assert response.json()["finished"] == (status == "error")
    assert response["Cache-Control"] == "private, no-store"


def test_parsing_finished_is_not_search_ready_until_embeddings_exist(client, owner):
    document = make_document(owner)
    make_chunks(document, 2)
    url = reverse("documents:status", args=[document.pk])
    response = client.get(url).json()
    assert response["state"] == "embedding"
    assert response["stage"] == 3
    assert response["text_ready"]
    assert not response["finished"]
    document.chunks.update(embedding=[0.1] * 1536)
    response = client.get(url).json()
    assert response["state"] == "ready"
    assert response["stage"] == 4
    assert response["finished"]


@pytest.mark.parametrize("visitor", ["other", "public", "admin", "anonymous"])
def test_progress_endpoint_protects_document_permissions(client, owner, visitor):
    document = make_document(owner, is_public=visitor == "public")
    if visitor == "anonymous":
        client.logout()
    else:
        client.force_login(make_user("visitor", role="admin" if visitor == "admin" else "viewer"))
    response = client.get(reverse("documents:status", args=[document.pk]))
    assert response.status_code == {"other": 403, "anonymous": 302}.get(visitor, 200)


def test_missing_progress_document_returns_404(client, owner):
    assert client.get(reverse("documents:status", args=[999999])).status_code == 404
