from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class ExpenseCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "지출 카테고리"
        verbose_name_plural = "지출 카테고리"

    def __str__(self) -> str:
        return self.name


class ExpenseRequest(models.Model):
    STATUS_SUBMITTED = "submitted"
    STATUS_UNDER_REVIEW = "under_review"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_PAID = "paid"
    STATUS_CHOICES = [
        (STATUS_SUBMITTED, "제출됨"),
        (STATUS_UNDER_REVIEW, "검토중"),
        (STATUS_APPROVED, "승인"),
        (STATUS_REJECTED, "반려"),
        (STATUS_PAID, "지급 완료"),
    ]

    SYNC_NOT_READY = "not_ready"
    SYNC_PENDING = "pending"
    SYNC_SUCCESS = "success"
    SYNC_FAILED = "failed"
    SYNC_CHOICES = [
        (SYNC_NOT_READY, "대기"),
        (SYNC_PENDING, "진행중"),
        (SYNC_SUCCESS, "성공"),
        (SYNC_FAILED, "실패"),
    ]

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="expense_requests",
    )
    expense_date = models.DateField()
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT)
    amount_krw = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    comment = models.TextField(blank=True)
    current_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUBMITTED)
    admin_note = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    payment_date = models.DateField(null=True, blank=True)
    payment_memo = models.TextField(blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="paid_expense_requests",
    )
    google_drive_file_id = models.CharField(max_length=255, blank=True)
    google_drive_file_url = models.URLField(blank=True)
    google_sheet_row_ref = models.CharField(max_length=100, blank=True)
    sync_state = models.CharField(max_length=20, choices=SYNC_CHOICES, default=SYNC_NOT_READY)
    sync_error = models.TextField(blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "지출 요청"
        verbose_name_plural = "지출 요청"

    def __str__(self) -> str:
        return f"#{self.pk} {self.requester} {self.amount_krw:,}원"

    @property
    def primary_attachment(self):
        return self.attachments.first()

    @property
    def can_retry_sync(self) -> bool:
        return self.current_status == self.STATUS_PAID and self.sync_state == self.SYNC_FAILED


def expense_attachment_upload_to(instance: "ExpenseAttachment", filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return f"expense_attachments/{instance.request_id}/{instance.request_id}_{instance.pk or 'new'}{suffix}"


class ExpenseAttachment(models.Model):
    request = models.ForeignKey(ExpenseRequest, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=expense_attachment_upload_to)
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100)
    file_size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "지출 첨부파일"
        verbose_name_plural = "지출 첨부파일"


class ExpenseStatusHistory(models.Model):
    request = models.ForeignKey(ExpenseRequest, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, choices=ExpenseRequest.STATUS_CHOICES)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="expense_status_changes",
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "지출 상태 이력"
        verbose_name_plural = "지출 상태 이력"


class SyncLog(models.Model):
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"
    STATUS_CHOICES = [
        (STATUS_SUCCESS, "성공"),
        (STATUS_FAILED, "실패"),
        (STATUS_SKIPPED, "건너뜀"),
    ]

    SERVICE_DRIVE = "drive"
    SERVICE_SHEETS = "sheets"
    SERVICE_COMBINED = "combined"
    SERVICE_CHOICES = [
        (SERVICE_DRIVE, "Google Drive"),
        (SERVICE_SHEETS, "Google Sheets"),
        (SERVICE_COMBINED, "통합"),
    ]

    request = models.ForeignKey(ExpenseRequest, on_delete=models.CASCADE, related_name="sync_logs")
    service = models.CharField(max_length=20, choices=SERVICE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    action = models.CharField(max_length=100)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "동기화 로그"
        verbose_name_plural = "동기화 로그"
