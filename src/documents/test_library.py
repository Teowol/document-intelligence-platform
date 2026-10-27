import pytest
from django.urls import reverse
from conftest import make_document, make_user

pytestmark = pytest.mark.django_db


def test_library_filters_and_counts_respect_access(client):
    user, other = make_user(), make_user('other')
    own = make_document(user, title='Annual report', size_bytes=100)
    make_document(other, title='Annual report private', size_bytes=900)
    shared = make_document(other, title='Shared notes', is_public=True, doc_type='txt', status='processing', size_bytes=200)
    client.force_login(user)
    response = client.get(reverse('documents:list'), {'q': 'Annual', 'type': 'pdf', 'status': 'ready'})
    assert response.status_code == 200
    assert list(response.context['object_list']) == [own]
    assert response.context['library'] == {'total': 2, 'size': 300, 'ready': 1, 'pending': 1, 'errors': 0}
    assert 'Annual report private' not in response.content.decode()
    response = client.get(reverse('documents:list'), {'q': 'Shared', 'type': 'txt', 'status': 'processing'})
    assert list(response.context['object_list']) == [shared]


def test_library_search_filename_sort_and_pagination(client):
    user = make_user()
    for index in range(14):
        make_document(user, title=f'Report {index:02}', original_filename='budget.pdf', size_bytes=index)
    client.force_login(user)
    response = client.get(reverse('documents:list'), {'q': 'budget', 'sort': 'size', 'type': 'pdf', 'page': 2})
    assert response.status_code == 200
    assert [doc.size_bytes for doc in response.context['object_list']] == [1, 0]
    assert response.context['filter_params'] == 'q=budget&sort=size&type=pdf'
    assert response.context['paginator'].count == 14


def test_library_empty_and_invalid_filters(client):
    client.force_login(make_user())
    response = client.get(reverse('documents:list'), {'sort': 'invalid', 'status': 'invalid', 'type': 'invalid'})
    assert response.status_code == 200
    assert response.context['library']['total'] == 0
    assert response.context['paginator'].count == 0


def test_library_admin_sees_all_documents(client):
    admin, other = make_user(role='admin'), make_user('other')
    private = make_document(other)
    client.force_login(admin)
    response = client.get(reverse('documents:list'))
    assert list(response.context['object_list']) == [private]
    assert response.context['library']['total'] == 1
