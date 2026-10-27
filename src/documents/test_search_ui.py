from unittest.mock import patch
import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from conftest import make_user

pytestmark = pytest.mark.django_db


def test_search_empty_does_not_call_provider(client):
    client.force_login(make_user())
    with patch('documents.views.search_semantic') as search:
        response = client.get(reverse('documents:search'))
    assert response.status_code == 200
    search.assert_not_called()
    assert b'data-live-search' in response.content
    assert b'Enter a query to search your documents semantically.' not in response.content


@pytest.mark.parametrize('failure', [PermissionDenied(), RuntimeError('private provider detail')])
def test_search_errors_render_in_results(client, failure):
    client.force_login(make_user())
    with patch('documents.views.search_semantic', side_effect=failure):
        response = client.get(reverse('documents:search'), {'q': 'budget'})
    assert response.status_code == 200
    assert response.context['search_error']
    assert b'private provider detail' not in response.content
    assert b'id="search-results"' in response.content
