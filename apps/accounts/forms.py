from django import forms
from django.contrib.auth.forms import UserCreationForm

from apps.accounts.models import User
from apps.expenses.models import ExpenseCategory


class MemberCreateForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "first_name", "email", "role")
        labels = {
            "username": "아이디",
            "first_name": "이름",
            "email": "이메일",
            "role": "권한",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].label = "비밀번호"
        self.fields["password2"].label = "비밀번호 확인"
        for name, field in self.fields.items():
            if name == "role":
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")


class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ("name", "sort_order", "is_active")
        labels = {
            "name": "카테고리명",
            "sort_order": "정렬순서",
            "is_active": "사용 여부",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs.setdefault("class", "form-check-input" if name == "is_active" else "form-control")
