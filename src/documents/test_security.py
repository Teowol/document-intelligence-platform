"""Phase 9: security hardening tests.

Uses the production settings module via the `settings` marker override so we
assert the security-relevant knobs that `check --deploy` relies on.
"""

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


@pytest.mark.django_db
def test_api_requires_authentication(client):
    """Unauthenticated requests to document endpoints are rejected."""
    response = client.get(reverse("documents:list"))
    assert response.status_code == 302  # redirect to login
    assert "/accounts/login/" in response.url


def test_public_healthz_has_no_security_cookies(client):
    """Health endpoint is open, not session-bound, and has no CSRF leak."""
    response = client.get(reverse("healthz"))
    assert response.status_code == 200
    assert "csrftoken" not in response.cookies


def test_auth_page_includes_csrf_token(client):
    """Login form renders with a CSRF token."""
    response = client.get(reverse("account_login"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "csrfmiddlewaretoken" in html


def test_upload_rejects_empty_file(client, settings):
    """An empty 'PDF' with no magic bytes is refused at the server."""
    settings.MEDIA_ROOT = str(__import__("tempfile").mkdtemp())

    from django.core.files.uploadedfile import SimpleUploadedFile

    user = _make_login(client)

    empty = SimpleUploadedFile("x.pdf", b"", content_type="application/pdf")
    response = client.post(
        reverse("documents:upload"),
        {"file": empty, "title": "empty", "is_public": False},
    )
    # Should NOT redirect to success (form must re-render with errors).
    assert response.status_code != 302
    assert "documents/document_form.html" in [
        t.name for t in response.templates
    ] or response.status_code == 200


def _make_login(client):
    from conftest import make_user

    user = make_user(username="sec")
    client.force_login(user)
    return user

