from django.urls import path

from apps.accounts.views import AdminSettingsView, ToggleMemberActiveView

urlpatterns = [
    path("", AdminSettingsView.as_view(), name="admin-settings"),
    path("users/<int:pk>/toggle/", ToggleMemberActiveView.as_view(), name="toggle-member-active"),
]
