from django import forms
from django.conf import settings
from pathlib import Path

from apps.expenses.models import ExpenseCategory, ExpenseRequest

ALLOWED_ATTACHMENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/heic",
    "image/heif",
}


class ExpenseRequestForm(forms.ModelForm):
    attachment = forms.FileField(label="영수증/사진", required=False)

    class Meta:
        model = ExpenseRequest
        fields = ("expense_date", "category", "amount_krw", "comment")
        widgets = {
            "expense_date": forms.DateInput(attrs={"type": "date"}),
            "comment": forms.Textarea(attrs={"rows": 4}),
        }
        labels = {
            "expense_date": "지출 일자",
            "category": "사유 분류",
            "amount_krw": "청구 금액 (원)",
            "comment": "비고",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = ExpenseCategory.objects.filter(is_active=True)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        self.fields["category"].widget.attrs["class"] = "form-select"
        self.fields["attachment"].widget.attrs["class"] = "form-control"

    def clean_attachment(self):
        file = self.cleaned_data.get("attachment")
        if not file:
            return file
        if file.size > settings.EXPENSE_ATTACHMENT_MAX_BYTES:
            raise forms.ValidationError("첨부 파일 용량이 너무 큽니다.")
        content_type = getattr(file, "content_type", "") or ""
        extension = Path(file.name).suffix.lower()
        if content_type not in ALLOWED_ATTACHMENT_TYPES and extension not in {".jpg", ".jpeg", ".png", ".heic", ".heif"}:
            raise forms.ValidationError("jpg, png, heic 형식만 업로드할 수 있습니다.")
        return file


class ExpenseFilterForm(forms.Form):
    status = forms.ChoiceField(label="상태", required=False)
    requester = forms.CharField(label="신청자", required=False)
    category = forms.ModelChoiceField(label="카테고리", queryset=ExpenseCategory.objects.all(), required=False)
    date_from = forms.DateField(label="시작일", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(label="종료일", required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = [("", "전체")] + ExpenseRequest.STATUS_CHOICES
        for name, field in self.fields.items():
            field.widget.attrs.setdefault("class", "form-select" if name in {"status", "category"} else "form-control")


class ReviewActionForm(forms.Form):
    note = forms.CharField(label="관리자 메모", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["note"].widget.attrs.setdefault("class", "form-control")


class RejectActionForm(forms.Form):
    rejection_reason = forms.CharField(
        label="반려 사유",
        required=True,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    note = forms.CharField(label="관리자 메모", required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class MarkPaidForm(forms.Form):
    payment_date = forms.DateField(label="지급일", widget=forms.DateInput(attrs={"type": "date"}))
    payment_memo = forms.CharField(label="지급 메모", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
