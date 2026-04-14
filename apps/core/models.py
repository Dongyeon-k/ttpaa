from django.db import models


class NotificationLog(models.Model):
    CHANNEL_EMAIL = "email"
    CHANNEL_CHOICES = [(CHANNEL_EMAIL, "이메일")]

    event_type = models.CharField(max_length=100)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_EMAIL)
    recipient = models.EmailField()
    subject = models.CharField(max_length=255)
    body = models.TextField()
    related_label = models.CharField(max_length=100, blank=True)
    related_object_id = models.CharField(max_length=50, blank=True)
    success = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "알림 로그"
        verbose_name_plural = "알림 로그"
