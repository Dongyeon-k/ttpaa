from django.urls import path

from apps.expenses.views import (
    AdminExpenseDetailView,
    AdminExpenseQueueView,
    ExpenseCreateView,
    ExpenseRetrySyncView,
    ExpenseTransitionView,
    MyExpenseListView,
)

urlpatterns = [
    path("new/", ExpenseCreateView.as_view(), name="expense-create"),
    path("mine/", MyExpenseListView.as_view(), name="expense-my-list"),
    path("admin/queue/", AdminExpenseQueueView.as_view(), name="expense-admin-queue"),
    path("admin/<int:pk>/", AdminExpenseDetailView.as_view(), name="expense-admin-detail"),
    path("admin/<int:pk>/transition/<str:target_status>/", ExpenseTransitionView.as_view(), name="expense-transition"),
    path("admin/<int:pk>/retry-sync/", ExpenseRetrySyncView.as_view(), name="expense-retry-sync"),
]
