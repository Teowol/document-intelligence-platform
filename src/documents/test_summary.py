from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.urls import reverse

from conftest import make_chunks, make_document, make_user
from documents.forms import DocumentUploadForm
from documents.summary import generate_summary

pytestmark = pytest.mark.django_db


@pytest.fixture
def scenario(client, monkeypatch):
    user = make_user()
    document = make_document(user)
    make_chunks(document)
    client.force_login(user)
    generator = Mock(return_value={"text": "Document summary", "sampled": False})
    monkeypatch.setattr("documents.views.generate_summary", generator)
    return document, generator


def test_summary_cached_separately_for_each_language(client, scenario):
    document, generator = scenario
    url = reverse("documents:summary", args=[document.pk])
    assert client.post(url).status_code == 302
    client.post(url)
    assert generator.call_count == 1
    document.refresh_from_db()
    assert document.summaries["en"]["text"] == "Document summary"
    client.cookies["django_language"] = "tr"
    client.post(url)
    assert generator.call_count == 2
    assert generator.call_args.args[1] == "tr"
    document.refresh_from_db()
    assert set(document.summaries) == {"en", "tr"}


@pytest.mark.parametrize("viewer", ["other", "anonymous", "public", "admin"])
def test_summary_enforces_document_access(client, scenario, viewer):
    document, generator = scenario
    if viewer == "anonymous":
        client.logout()
    else:
        client.force_login(make_user("visitor", role="admin" if viewer == "admin" else "viewer"))
    if viewer == "public":
        document.is_public = True
        document.save(update_fields=["is_public"])
    response = client.post(reverse("documents:summary", args=[document.pk]))
    assert response.status_code == (403 if viewer == "other" else 302)
    assert generator.call_count == (1 if viewer in {"admin", "public"} else 0)


def test_opening_document_never_calls_summary_model(client, scenario):
    document, generator = scenario
    response = client.get(reverse("documents:detail", args=[document.pk]))
    html = response.content.decode()
    positions = [html.index(f'id="{section}-section"') for section in ["preview", "summary", "chunks", "file-info"]]
    assert positions == sorted(positions)
    assert 'id="preview-section" open' in html
    generator.assert_not_called()


def test_failed_summary_keeps_existing_languages(client, scenario):
    document, generator = scenario
    document.summaries = {"tr": {"text": "Existing", "sampled": False}}
    document.save(update_fields=["summaries"])
    generator.side_effect = RuntimeError("Unavailable")
    client.post(reverse("documents:summary", args=[document.pk]))
    document.refresh_from_db()
    assert set(document.summaries) == {"tr"}


def test_processing_document_cannot_be_summarized(client, scenario):
    document, generator = scenario
    document.status = "processing"
    document.save(update_fields=["status"])
    client.post(reverse("documents:summary", args=[document.pk]))
    generator.assert_not_called()


def test_generation_cannot_save_a_stale_summary(client, scenario):
    document, generator = scenario

    def reprocess(*args):
        document.status = "processing"
        document.save(update_fields=["status", "updated_at"])
        return {"text": "Stale summary", "sampled": False}

    generator.side_effect = reprocess
    client.post(reverse("documents:summary", args=[document.pk]))
    document.refresh_from_db()
    assert document.summaries == {}


def test_turkish_document_labels_and_forms(client, scenario):
    document, _ = scenario
    client.cookies["django_language"] = "tr"
    response = client.get(reverse("documents:detail", args=[document.pk]))
    html = response.content.decode()
    for label in ["Dosya önizlemesi", "Özet", "Parçalar", "Dosya bilgileri", "Hazır", "Görüntüleyici", 'data-label-dark="Koyu"']:
        assert label in html
    response = client.get(reverse("documents:upload"))
    for label in ["Belge başlığı", "Herkese açık belge"]:
        assert label in response.content.decode()


def test_summary_model_receives_bounded_excerpts_from_start_and_end(monkeypatch):
    document = make_document(make_user())
    make_chunks(document, count=100)
    completion = Mock(return_value=SimpleNamespace(choices=[
        SimpleNamespace(message=SimpleNamespace(content="Summary")),
    ]))
    monkeypatch.setattr("documents.summary._client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=completion)),
    ))
    result = generate_summary(document, "tr")
    assert result["sampled"]
    args = completion.call_args.kwargs
    assert "Turkish" in args["messages"][0]["content"]
    text = args["messages"][1]["content"]
    assert "chunk 0 of" in text and "chunk 99 of" in text


def test_empty_document_not_sent_to_model(monkeypatch):
    document = make_document(make_user())
    client = Mock()
    monkeypatch.setattr("documents.summary._client", client)
    with pytest.raises(ValueError):
        generate_summary(document, "en")
    client.assert_not_called()
