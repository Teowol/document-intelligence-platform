import io
import uuid

from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps

from .models import CustomUser


class ProfileForm(forms.ModelForm):
    avatar = forms.ImageField(required=False, label=_("Profile photo"), widget=forms.FileInput(
        attrs={"accept": "image/jpeg,image/png,image/webp", "class": "profile-file-input"},
    ))
    bio = forms.CharField(required=False, max_length=500, label=_("About you"),
                          widget=forms.Textarea(attrs={"rows": 4, "placeholder": _("A few words about yourself and your research interests.")}))
    remove_avatar = forms.BooleanField(required=False, label=_("Remove profile photo"),
                                      widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))

    class Meta:
        model = CustomUser
        fields = ["first_name", "last_name", "username", "bio", "avatar"]
        labels = {"first_name": _("First name"), "last_name": _("Last name"), "username": _("Username")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.previous_avatar_name = self.instance.avatar.name
        self.avatar_storage = self.instance.avatar.storage
        for name in ["first_name", "last_name", "username", "bio"]:
            self.fields[name].widget.attrs["class"] = "form-control"
        self.fields["first_name"].widget.attrs["autocomplete"] = "given-name"
        self.fields["last_name"].widget.attrs["autocomplete"] = "family-name"
        self.fields["username"].widget.attrs["autocomplete"] = "username"

    def clean_avatar(self):
        upload = self.cleaned_data.get("avatar")
        if not upload or "avatar" not in self.files:
            return upload
        if upload.size > 5 * 1024 * 1024:
            raise forms.ValidationError(_("Choose a photo smaller than 5 MB."))
        try:
            upload.seek(0)
            with Image.open(upload) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"}:
                    raise forms.ValidationError(_("Use a JPG, PNG, or WebP photo."))
                if image.width * image.height > 16_000_000:
                    raise forms.ValidationError(_("Choose a photo with at most 16 million pixels."))
                image = ImageOps.exif_transpose(image)
                image.thumbnail((512, 512))
                rgba = image.convert("RGBA")
                result = Image.new("RGB", rgba.size, "white")
                result.paste(rgba, mask=rgba.getchannel("A"))
                output = io.BytesIO()
                result.save(output, format="JPEG", quality=88, optimize=True)
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise forms.ValidationError(_("This photo could not be read. Please choose another image.")) from exc
        return SimpleUploadedFile(f"{uuid.uuid4().hex}.jpg", output.getvalue(), content_type="image/jpeg")

    def clean(self):
        data = super().clean()
        if data.get("remove_avatar") and "avatar" in self.files:
            raise forms.ValidationError(_("Choose a new photo or remove the existing one, not both."))
        return data
