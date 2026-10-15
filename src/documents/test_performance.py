"""Phase 9: performance regression tests (query-count / n+1 guards)."""

import pytest
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.db import connection

from conftest import make_chunks, make_document, make_user
from documents.views import DashboardView, DocumentListView

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return make_user(username="perf")


def test_dashboard_query_count_does_not_scale_with_chunks(user):
    """Chunk total must come from an aggregate, not per-document queries.

    With 12 docs each having chunks, the old n+1 pattern would issue >=12
    extra queries just for the chunk count. The fixed view stays bounded.
    """
    for _ in range(12):
        doc = make_document(user)
        make_chunks(doc)

    view = DashboardView.as_view()
    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    with CaptureQueriesContext(connection) as ctx:
        response = view(request)

    assert response.status_code == 200
    # Generous upper bound to avoid CI flakiness; the essential guarantee is
    # that query count does not grow ~linearly with the 12 documents.
    assert len(ctx) <= 9


def test_document_list_avoids_n_plus_one(user):
    """Each document card shows the owner, so owner must be select_related'd."""
    for i in range(6):
        make_document(user, title=f"doc{i}")

    view = DocumentListView.as_view()
    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    with CaptureQueriesContext(connection) as ctx:
        response = view(request)

    assert response.status_code == 200
    # A few queries for the page + one select_related for owners => no N+1.
    assert len(ctx) <= 6
