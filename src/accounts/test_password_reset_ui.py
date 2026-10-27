import pytest
from django.urls import reverse
from conftest import make_user

pytestmark = pytest.mark.django_db


def test_reset_form_and_login_link(client):
    url = reverse('account_reset_password')
    assert url in client.get(reverse('account_login')).content.decode()
    response = client.get(url)
    assert response.status_code == 200
    assert b'auth-shell' in response.content
    assert b'name="email"' in response.content
    response = client.post(url, {'email': 'invalid'})
    assert response.status_code == 200
    assert b'auth-field-errors' in response.content


def test_reset_request_uses_confirmation_template(client, mailoutbox, settings):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    user = make_user()
    response = client.post(reverse('account_reset_password'), {'email': user.email}, follow=True)
    assert response.status_code == 200
    assert 'account/password_reset_done.html' in [template.name for template in response.templates]
    assert b'auth-shell' in response.content
    assert len(mailoutbox) == 1
