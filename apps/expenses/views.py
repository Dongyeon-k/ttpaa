from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import CreateView, DetailView, ListView

from apps.core.permissions import AdminRequiredMixin
from apps.expenses.forms import (
    ExpenseFilterForm,
    ExpenseRequestForm,
    MarkPaidForm,
    RejectActionForm,
    ReviewActionForm,
)
from apps.expenses.models import ExpenseRequest
from apps.expenses.services import create_expense_request, sync_paid_request, transition_expense


class ExpenseCreateView(LoginRequiredMixin, CreateView):
    template_name = "expenses/expense_form.html"
    form_class = ExpenseRequestForm

    def form_valid(self, form):
        expense = create_expense_request(form=form, requester=self.request.user)
        messages.success(self.request, f"지출 요청 #{expense.pk} 이(가) 제출되었습니다.")
        return redirect("expense-my-list")


class MyExpenseListView(LoginRequiredMixin, ListView):
    template_name = "expenses/my_expense_list.html"
    context_object_name = "requests"

    def get_queryset(self):
        return ExpenseRequest.objects.select_related("category").filter(requester=self.request.user)


class AdminExpenseQueueView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    template_name = "expenses/admin_queue.html"
    context_object_name = "requests"

    def get_queryset(self):
        queryset = ExpenseRequest.objects.select_related("requester", "category", "paid_by")
        form = ExpenseFilterForm(self.request.GET or None)
        if form.is_valid():
            if form.cleaned_data.get("status"):
                queryset = queryset.filter(current_status=form.cleaned_data["status"])
            if form.cleaned_data.get("requester"):
                keyword = form.cleaned_data["requester"]
                queryset = queryset.filter(
                    Q(requester__first_name__icontains=keyword)
                    | Q(requester__username__icontains=keyword)
                    | Q(requester__email__icontains=keyword)
                )
            if form.cleaned_data.get("category"):
                queryset = queryset.filter(category=form.cleaned_data["category"])
            if form.cleaned_data.get("date_from"):
                queryset = queryset.filter(expense_date__gte=form.cleaned_data["date_from"])
            if form.cleaned_data.get("date_to"):
                queryset = queryset.filter(expense_date__lte=form.cleaned_data["date_to"])
        self.filter_form = form
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get("HX-Request"):
            return render(self.request, "expenses/partials/request_table.html", context)
        return super().render_to_response(context, **response_kwargs)


class AdminExpenseDetailView(LoginRequiredMixin, AdminRequiredMixin, DetailView):
    model = ExpenseRequest
    template_name = "expenses/admin_detail.html"
    context_object_name = "expense"

    def get_queryset(self):
        return ExpenseRequest.objects.select_related("requester", "category", "paid_by").prefetch_related(
            "attachments", "status_history", "sync_logs"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["review_form"] = ReviewActionForm(initial={"note": self.object.admin_note})
        context["reject_form"] = RejectActionForm(initial={"note": self.object.admin_note})
        context["paid_form"] = MarkPaidForm(initial={"payment_date": self.object.payment_date})
        return context


class ExpenseTransitionView(LoginRequiredMixin, AdminRequiredMixin, View):
    def post(self, request, pk: int, target_status: str):
        expense = get_object_or_404(ExpenseRequest, pk=pk)
        try:
            if target_status == ExpenseRequest.STATUS_UNDER_REVIEW:
                form = ReviewActionForm(request.POST)
                if form.is_valid():
                    transition_expense(
                        expense=expense,
                        to_status=target_status,
                        actor=request.user,
                        note=form.cleaned_data["note"],
                    )
                    messages.success(request, "검토중 상태로 변경했습니다.")
            elif target_status == ExpenseRequest.STATUS_APPROVED:
                form = ReviewActionForm(request.POST)
                if form.is_valid():
                    transition_expense(
                        expense=expense,
                        to_status=target_status,
                        actor=request.user,
                        note=form.cleaned_data["note"],
                    )
                    messages.success(request, "요청을 승인했습니다.")
            elif target_status == ExpenseRequest.STATUS_REJECTED:
                form = RejectActionForm(request.POST)
                if form.is_valid():
                    transition_expense(
                        expense=expense,
                        to_status=target_status,
                        actor=request.user,
                        note=form.cleaned_data["note"],
                        rejection_reason=form.cleaned_data["rejection_reason"],
                    )
                    messages.success(request, "요청을 반려했습니다.")
                else:
                    messages.error(request, "반려 사유를 입력해 주세요.")
            elif target_status == ExpenseRequest.STATUS_PAID:
                form = MarkPaidForm(request.POST)
                if form.is_valid():
                    expense = transition_expense(
                        expense=expense,
                        to_status=target_status,
                        actor=request.user,
                        payment_date=form.cleaned_data["payment_date"],
                        payment_memo=form.cleaned_data["payment_memo"],
                    )
                    try:
                        sync_paid_request(expense)
                        messages.success(request, "지급 완료 처리와 Google 동기화가 완료되었습니다.")
                    except Exception:
                        messages.warning(request, "지급 완료는 처리되었지만 Google 동기화에 실패했습니다. 다시 시도해 주세요.")
                else:
                    messages.error(request, "지급일을 확인해 주세요.")
            else:
                return HttpResponseBadRequest("지원하지 않는 상태입니다.")
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect("expense-admin-detail", pk=pk)


class ExpenseRetrySyncView(LoginRequiredMixin, AdminRequiredMixin, View):
    def post(self, request, pk: int):
        expense = get_object_or_404(ExpenseRequest, pk=pk)
        try:
            sync_paid_request(expense, force=True)
            messages.success(request, "Google 동기화를 다시 실행했습니다.")
        except Exception as exc:
            messages.error(request, f"동기화 재시도에 실패했습니다: {exc}")
        return redirect("expense-admin-detail", pk=pk)
