from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView
from django.urls import include, path

from apps.core.views import DashboardView, HealthCheckView
from apps.pwa.views import ManifestView, ServiceWorkerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", DashboardView.as_view(), name="dashboard"),
    path("health/", HealthCheckView.as_view(), name="health"),
    path("offline/", TemplateView.as_view(template_name="pwa/offline.html"), name="offline"),
    path("expenses/", include("apps.expenses.urls")),
    path("chatbot/", include("apps.chatbot.urls")),
    path("settings/", include("apps.accounts.urls")),
    path("manifest.json", ManifestView.as_view(), name="manifest"),
    path("service-worker.js", ServiceWorkerView.as_view(), name="service-worker"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
