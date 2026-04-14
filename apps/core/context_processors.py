from django.conf import settings


def app_settings(request):
    return {
        "APP_BASE_URL": settings.APP_BASE_URL,
    }
