from datetime import timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from conftest import make_chunks, make_document, make_user
from documents.models import Document, QAHistory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean_dashboard_cache():
    cache.clear()


def test_dashboard_counts_only_accessible_documents(client):
    user, other = make_user(), make_user("other")
    own = make_document(user, size_bytes=100)
    shared = make_document(other, doc_type="txt", is_public=True, status="processing", size_bytes=200)
    private = make_document(other, size_bytes=500)
    Document.objects.filter(pk=own.pk).update(created_at=timezone.now() - timedelta(days=8))
    for document, count in [(own, 3), (shared, 2), (private, 4)]:
        make_chunks(document, count)
    client.force_login(user)
    response = client.get(reverse("documents:dashboard"))
    assert response.status_code == 200
    context = response.context
    assert context["total_docs"] == 2
    assert context["visible_chunks"] == 5
    assert context["total_size"] == 300
    assert context["ready_rate"] == 50
    assert context["new_this_week"] == 1
    assert sum(item["count"] for item in context["type_breakdown"]) == 2
    assert {doc.pk for doc in context["recent_documents"]} == {own.pk, shared.pk}


def test_dashboard_history_is_personal_and_checks_source_access(client):
    user, other = make_user(), make_user("other")
    own = QAHistory.objects.create(owner=user, question="My question", answer="A")
    hidden = QAHistory.objects.create(owner=user, question="Revoked source", answer="B")
    hidden.documents.add(make_document(other))
    QAHistory.objects.create(owner=other, question="Someone else's question", answer="C")
    client.force_login(user)
    response = client.get(reverse("documents:dashboard"))
    assert [chat.pk for chat in response.context["recent_chats"]] == [own.pk]


def test_empty_dashboard_has_zero_counts_and_upload_action(client):
    client.force_login(make_user())
    response = client.get(reverse("documents:dashboard"))
    assert response.context["total_docs"] == 0
    assert response.context["ready_rate"] == 0
    assert response.context["type_breakdown"] == []
    assert reverse("documents:upload") in response.content.decode()
