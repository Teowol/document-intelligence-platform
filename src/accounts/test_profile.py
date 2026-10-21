import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from accounts.models import CustomUser

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(client):
    user = CustomUser.objects.create_user(username="profileuser", email="profile@example.com", password="Test-Password-123!")
    client.force_login(user)
    return user


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


def photo(format="PNG", size=(800, 600)):
    output = io.BytesIO()
    Image.new("RGB", size, "navy").save(output, format=format)
    return SimpleUploadedFile(f"photo.{format.lower()}", output.getvalue(), content_type=f"image/{format.lower()}")


def test_profile_updates_only_editable_fields(client, owner):
    response = client.post(reverse("accounts:profile"), {
        "first_name": "Ada", "last_name": "Lovelace", "username": "ada", "bio": "Research notes",
        "email": "attacker@example.com", "role": "admin", "is_staff": "true", "is_superuser": "true",
    })
    assert response.status_code == 302
    owner.refresh_from_db()
    assert owner.first_name == "Ada" and owner.last_name == "Lovelace"
    assert owner.username == "ada" and owner.bio == "Research notes"
    assert owner.email == "profile@example.com" and owner.role == "viewer"
    assert not owner.is_staff and not owner.is_superuser


def test_photo_is_resized_reencoded_and_served_privately(client, owner):
    response = client.post(reverse("accounts:profile"), {"username": owner.username, "avatar": photo()})
    assert response.status_code == 302
    owner.refresh_from_db()
    with owner.avatar.open("rb") as file:
        image = Image.open(file)
        assert image.format == "JPEG" and max(image.size) <= 512
        assert not image.getexif()
    response = client.get(reverse("accounts:avatar"))
    assert response.status_code == 200
    assert response["Content-Type"] == "image/jpeg"
    assert response["Cache-Control"] == "private, no-store"
    response.close()


@pytest.mark.parametrize("remove", [False, True])
def test_replaced_or_removed_photo_is_cleaned_after_save(client, owner, django_capture_on_commit_callbacks, remove):
    client.post(reverse("accounts:profile"), {"username": owner.username, "avatar": photo()})
    owner.refresh_from_db()
    previous = owner.avatar.name
    storage = owner.avatar.storage
    data = {"username": owner.username, "remove_avatar": "on"} if remove else {"username": owner.username, "avatar": photo()}
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(reverse("accounts:profile"), data)
    assert response.status_code == 302
    assert not storage.exists(previous)
    owner.refresh_from_db()
    assert bool(owner.avatar) == (not remove)
    if remove:
        assert client.get(reverse("accounts:avatar")).status_code == 404


@pytest.mark.parametrize("kind", ["gif", "text", "oversized"])
def test_invalid_photos_are_rejected_without_updating_profile(client, owner, kind):
    if kind == "gif":
        upload = photo("GIF")
    elif kind == "text":
        upload = SimpleUploadedFile("fake.jpg", b"not an image")
    else:
        upload = photo()
        upload = SimpleUploadedFile("big.png", upload.read() + b"x" * (5 * 1024 * 1024))
    response = client.post(reverse("accounts:profile"), {"username": owner.username, "first_name": "Unsaved", "avatar": upload})
    assert response.status_code == 200
    assert response.context["form"].errors.get("avatar")
    owner.refresh_from_db()
    assert not owner.avatar and not owner.first_name


def test_duplicate_username_and_long_bio_keep_existing_profile(client, owner):
    CustomUser.objects.create_user(username="taken", email="taken@example.com")
    response = client.post(reverse("accounts:profile"), {"username": "taken", "bio": "x" * 501})
    assert set(response.context["form"].errors) == {"username", "bio"}
    owner.refresh_from_db()
    assert owner.username == "profileuser" and owner.bio == ""


def test_profile_and_avatar_require_login(client):
    assert client.get(reverse("accounts:profile")).status_code == 302
    assert client.post(reverse("accounts:profile"), {"username": "hacker"}).status_code == 302
    assert client.get(reverse("accounts:avatar")).status_code == 302


def test_other_users_cannot_fetch_profile_photo(client, owner):
    client.post(reverse("accounts:profile"), {"username": owner.username, "avatar": photo()})
    other = CustomUser.objects.create_user(username="other", email="other@example.com")
    client.force_login(other)
    assert client.get(reverse("accounts:avatar"), {"user": owner.pk}).status_code == 404


def test_profile_is_localized_and_security_pages_render(client, owner):
    client.cookies["django_language"] = "tr"
    response = client.get(reverse("accounts:profile"))
    assert response.status_code == 200
    assert "Profilinizi kişiselleştirin" in response.content.decode()
    assert response["Cache-Control"] == "private, no-store"
    for route in ["account_email", "account_change_password"]:
        assert client.get(reverse(route)).status_code == 200


def test_email_changes_use_allauth_flow(client, owner, settings):
    from allauth.account.models import EmailAddress

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    EmailAddress.objects.create(user=owner, email=owner.email, primary=True, verified=True)
    response = client.post(reverse("account_email"), {"email": "new@example.com", "action_add": ""})
    assert response.status_code == 302
    assert EmailAddress.objects.filter(user=owner, email="new@example.com").exists()
    owner.refresh_from_db()
    assert owner.email == "profile@example.com"
