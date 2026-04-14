from django import forms

from apps.chatbot.models import ConstitutionDocument


class ConstitutionUploadForm(forms.ModelForm):
    class Meta:
        model = ConstitutionDocument
        fields = ("version_label", "file")
        labels = {
            "version_label": "버전명",
            "file": "PDF 파일",
        }

    def clean_file(self):
        file = self.cleaned_data["file"]
        content_type = getattr(file, "content_type", "") or ""
        if content_type != "application/pdf" and not file.name.lower().endswith(".pdf"):
            raise forms.ValidationError("PDF 파일만 업로드할 수 있습니다.")
        return file

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class ChatQuestionForm(forms.Form):
    question = forms.CharField(
        label="질문",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "회칙에 대한 질문을 입력해 주세요.",
            }
        ),
    )
