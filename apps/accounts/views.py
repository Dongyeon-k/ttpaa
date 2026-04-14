from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.forms import ExpenseCategoryForm, MemberCreateForm
from apps.accounts.models import User
from apps.chatbot.models import ConstitutionDocument
from apps.core.permissions import AdminRequiredMixin
from apps.expenses.models import ExpenseCategory, ExpenseRequest


class AdminSettingsView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    template_name = "accounts/admin_settings.html"
    success_url = reverse_lazy("admin-settings")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["member_form"] = kwargs.get("member_form") or MemberCreateForm()
        context["category_form"] = kwargs.get("category_form") or ExpenseCategoryForm()
        context["members"] = User.objects.order_by("role", "first_name", "username")
        context["categories"] = ExpenseCategory.objects.order_by("sort_order", "name")
        context["request_summary"] = ExpenseRequest.objects.values("current_status").annotate(count=Count("id"))
        context["active_constitution"] = ConstitutionDocument.objects.filter(is_active=True).first()
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")
        if action == "create_member":
            member_form = MemberCreateForm(request.POST)
            if member_form.is_valid():
                member = member_form.save(commit=False)
                member.is_active = True
                member.save()
                messages.success(request, "구성원 계정이 생성되었습니다.")
                return redirect(self.success_url)
            return self.render_to_response(self.get_context_data(member_form=member_form))

        if action == "create_category":
            category_form = ExpenseCategoryForm(request.POST)
            if category_form.is_valid():
                category_form.save()
                messages.success(request, "지출 카테고리가 추가되었습니다.")
                return redirect(self.success_url)
            return self.render_to_response(self.get_context_data(category_form=category_form))

        messages.error(request, "알 수 없는 요청입니다.")
        return redirect(self.success_url)


class ToggleMemberActiveView(LoginRequiredMixin, AdminRequiredMixin, View):
    def post(self, request, pk: int):
        member = get_object_or_404(User, pk=pk)
        if member == request.user:
            messages.error(request, "본인 계정은 비활성화할 수 없습니다.")
            return redirect("admin-settings")
        member.is_active = not member.is_active
        member.save(update_fields=["is_active"])
        messages.success(request, "계정 상태가 변경되었습니다.")
        return redirect("admin-settings")
