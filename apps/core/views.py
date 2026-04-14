import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.chatbot.models import ConstitutionDocument
from apps.expenses.models import ExpenseRequest

logger = logging.getLogger("ttpaa")


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        if self.request.user.is_portal_admin:
            context["pending_count"] = ExpenseRequest.objects.filter(
                current_status__in=[ExpenseRequest.STATUS_SUBMITTED, ExpenseRequest.STATUS_UNDER_REVIEW]
            ).count()
            context["approved_unpaid_count"] = ExpenseRequest.objects.filter(
                current_status=ExpenseRequest.STATUS_APPROVED
            ).count()
            context["paid_this_month_count"] = ExpenseRequest.objects.filter(
                current_status=ExpenseRequest.STATUS_PAID,
                payment_date__year=today.year,
                payment_date__month=today.month,
            ).count()
            context["recent_requests"] = ExpenseRequest.objects.select_related("requester", "category")[:5]
        else:
            context["my_open_count"] = ExpenseRequest.objects.filter(
                requester=self.request.user
            ).exclude(current_status__in=[ExpenseRequest.STATUS_REJECTED, ExpenseRequest.STATUS_PAID]).count()
            context["my_recent_requests"] = ExpenseRequest.objects.filter(requester=self.request.user)[:5]
            context["recent_requests"] = ExpenseRequest.objects.select_related("requester", "category").filter(
                requester=self.request.user
            )[:5]
        context["status_summary"] = ExpenseRequest.objects.values("current_status").annotate(count=Count("id"))
        context["active_constitution"] = ConstitutionDocument.objects.filter(is_active=True).first()
        return context


class HealthCheckView(View):
    def get(self, request):
        logger.info("health_check ok")
        return JsonResponse({"status": "ok"})
