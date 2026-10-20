from unittest.mock import Mock

import pytest
from django.urls import reverse

from conftest import make_document, make_user
from documents.models import QAHistory

pytestmark = pytest.mark.django_db


@pytest.fixture
def scenario(client, monkeypatch):
    user = make_user()
    document = make_document(user, original_filename="react.pdf")
    client.force_login(user)
    answer = Mock(return_value={
        "answer": "React answer", "sources": [{"file": "react.pdf", "page": 1}],
        "tool_rounds": 0, "document_ids": [document.pk],
    })
    monkeypatch.setattr("documents.views.answer_question", answer)
    return user, document, answer


def test_question_saved_and_reopening_does_not_call_model(client, scenario):
    user, document, answer = scenario
    url = reverse("documents:ask")
    response = client.post(url, {"q": "What is React?"})
    entry = QAHistory.objects.get(owner=user)
    assert response.url == f"{url}?chat={entry.pk}"
    assert entry.documents.get() == document
    assert entry.question == "What is React?"
    assert entry.sources == [{"file": "react.pdf", "page": 1}]
    response = client.get(response.url)
    assert response.status_code == 200
    assert b"React answer" in response.content
    client.get(response.request["PATH_INFO"], {"chat": entry.pk})
    assert answer.call_count == 1
    assert QAHistory.objects.count() == 1


def test_get_queries_do_not_spend_tokens_or_create_history(client, scenario):
    response = client.get(reverse("documents:ask"), {"q": "old query"})
    assert response.status_code == 200
    scenario[2].assert_not_called()
    assert not QAHistory.objects.exists()
    assert b"Q3 revenue?" not in response.content
    assert b"Key topics?" not in response.content


def test_history_is_private_even_to_another_admin(client, scenario):
    user, document, _ = scenario
    entry = QAHistory.objects.create(owner=user, question="Private question", answer="Secret")
    entry.documents.add(document)
    client.force_login(make_user("admin", role="admin"))
    url = reverse("documents:ask")
    assert client.get(url, {"chat": entry.pk}).status_code == 404
    assert client.get(url, {"history": "1"}).json()["entries"] == []


@pytest.mark.parametrize("bulk", [False, True])
def test_source_deletion_removes_linked_history_only(client, scenario, bulk):
    user, document, _ = scenario
    other = make_document(user)
    linked = QAHistory.objects.create(owner=user, question="React", answer="A")
    linked.documents.add(document, other)
    unrelated = QAHistory.objects.create(owner=user, question="Other", answer="B")
    unrelated.documents.add(other)
    if bulk:
        type(document).objects.filter(pk=document.pk).delete()
    else:
        document.delete()
    assert not QAHistory.objects.filter(pk=linked.pk).exists()
    assert QAHistory.objects.filter(pk=unrelated.pk).exists()
    response = client.get(reverse("documents:ask"), {"history": "1", "chat": linked.pk})
    assert response.json()["selected_exists"] is False
    assert [entry["id"] for entry in response.json()["entries"]] == [unrelated.pk]


def test_public_source_owner_deletion_cleans_other_users_history(client, scenario):
    user, _, _ = scenario
    source_owner = make_user("source")
    public = make_document(source_owner, is_public=True)
    entry = QAHistory.objects.create(owner=user, question="Public source", answer="A")
    entry.documents.add(public)
    source_owner.delete()
    assert not QAHistory.objects.filter(pk=entry.pk).exists()


def test_revoked_source_access_hides_saved_answer(client, scenario):
    user, _, _ = scenario
    document = make_document(make_user("source"), is_public=True)
    entry = QAHistory.objects.create(owner=user, question="Shared file", answer="Secret")
    entry.documents.add(document)
    document.is_public = False
    document.save(update_fields=["is_public"])
    url = reverse("documents:ask")
    assert client.get(url, {"chat": entry.pk}).status_code == 404
    assert client.get(url, {"history": "1"}).json()["entries"] == []


@pytest.mark.parametrize("question", ["", "   ", "x" * 4001])
def test_invalid_question_not_sent_to_model(client, scenario, question):
    assert client.post(reverse("documents:ask"), {"q": question}).status_code == 400
    scenario[2].assert_not_called()
    assert not QAHistory.objects.exists()


def test_failed_answer_not_saved(client, scenario):
    scenario[2].side_effect = RuntimeError("API error")
    response = client.post(reverse("documents:ask"), {"q": "React?"})
    assert response.status_code == 502
    assert not QAHistory.objects.exists()


def test_document_deleted_while_generating_not_saved(client, scenario):
    _, document, answer = scenario
    result = answer.return_value

    def delete_then_answer(*args, **kwargs):
        document.delete()
        return result

    answer.side_effect = delete_then_answer
    response = client.post(reverse("documents:ask"), {"q": "React?"})
    assert response.status_code == 502
    assert not QAHistory.objects.exists()


def test_history_html_and_json_do_not_cache(client, scenario):
    for params in ({}, {"history": "1"}):
        response = client.get(reverse("documents:ask"), params)
        assert response["Cache-Control"] == "private, no-store"


def test_history_requires_login(client):
    url = reverse("documents:ask")
    assert client.get(url, {"history": "1"}).status_code == 302
    assert client.post(url, {"q": "React?"}).status_code == 302


def test_rate_limited_question_not_saved(client, scenario, monkeypatch):
    from django.core.exceptions import PermissionDenied

    monkeypatch.setattr("documents.views.require_rate_limit", Mock(side_effect=PermissionDenied))
    assert client.post(reverse("documents:ask"), {"q": "React?"}).status_code == 429
    scenario[2].assert_not_called()
    assert not QAHistory.objects.exists()
