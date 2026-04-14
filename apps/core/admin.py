from django.contrib import admin

from apps.core.models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("event_type", "recipient", "success", "created_at")
    list_filter = ("event_type", "success", "created_at")
    search_fields = ("recipient", "subject", "related_label", "related_object_id")
