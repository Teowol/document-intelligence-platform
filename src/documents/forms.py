from django import forms

from .models import Document


class QAQuestionForm(forms.Form):
    q = forms.CharField(max_length=4000)


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["file", "title", "is_public"]
        widgets = {
            "title": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Document title"}
            ),
            "file": forms.FileInput(attrs={"class": "form-control"}),
            "is_public": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_title(self):
        title = self.cleaned_data.get("title", "").strip()
        if not title:
            file = self.cleaned_data.get("file")
            if file:
                title = file.name  # fall back to the uploaded file's name
        return title
