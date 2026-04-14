from django.conf import settings
from django.db import models


class ConstitutionDocument(models.Model):
    STATUS_PENDING = "pending"
    STATUS_INDEXED = "indexed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "대기"),
        (STATUS_INDEXED, "인덱싱 완료"),
        (STATUS_FAILED, "실패"),
    ]

    version_label = models.CharField(max_length=100)
    file = models.FileField(upload_to="constitutions/")
    upload_filename = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="uploaded_constitutions"
    )
    is_active = models.BooleanField(default=True)
    index_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    index_error = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    indexed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "회칙 문서"
        verbose_name_plural = "회칙 문서"

    def __str__(self) -> str:
        return self.version_label


class ConstitutionPage(models.Model):
    document = models.ForeignKey(ConstitutionDocument, on_delete=models.CASCADE, related_name="pages")
    page_number = models.PositiveIntegerField()
    text = models.TextField()

    class Meta:
        ordering = ["page_number"]
        unique_together = ("document", "page_number")
        verbose_name = "회칙 페이지"
        verbose_name_plural = "회칙 페이지"


class ConstitutionChunk(models.Model):
    document = models.ForeignKey(ConstitutionDocument, on_delete=models.CASCADE, related_name="chunks")
    page = models.ForeignKey(ConstitutionPage, on_delete=models.CASCADE, related_name="chunks")
    page_number = models.PositiveIntegerField()
    chunk_index = models.PositiveIntegerField()
    heading = models.CharField(max_length=255, blank=True)
    text = models.TextField()

    class Meta:
        ordering = ["page_number", "chunk_index"]
        unique_together = ("document", "page_number", "chunk_index")
        verbose_name = "회칙 청크"
        verbose_name_plural = "회칙 청크"


class ChatQueryLog(models.Model):
    document = models.ForeignKey(ConstitutionDocument, null=True, blank=True, on_delete=models.SET_NULL)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    question = models.TextField()
    supported = models.BooleanField(default=False)
    answer_text = models.TextField(blank=True)
    refusal_reason = models.TextField(blank=True)
    raw_response_json = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "챗봇 질의 로그"
        verbose_name_plural = "챗봇 질의 로그"
