from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ExpenseCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["sort_order", "name"],
                "verbose_name": "지출 카테고리",
                "verbose_name_plural": "지출 카테고리",
            },
        ),
        migrations.CreateModel(
            name="ExpenseRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("expense_date", models.DateField()),
                ("amount_krw", models.PositiveIntegerField(validators=[MinValueValidator(1)])),
                ("comment", models.TextField(blank=True)),
                ("current_status", models.CharField(choices=[("submitted", "제출됨"), ("under_review", "검토중"), ("approved", "승인"), ("rejected", "반려"), ("paid", "지급 완료")], default="submitted", max_length=20)),
                ("admin_note", models.TextField(blank=True)),
                ("rejection_reason", models.TextField(blank=True)),
                ("payment_date", models.DateField(blank=True, null=True)),
                ("payment_memo", models.TextField(blank=True)),
                ("google_drive_file_id", models.CharField(blank=True, max_length=255)),
                ("google_drive_file_url", models.URLField(blank=True)),
                ("google_sheet_row_ref", models.CharField(blank=True, max_length=100)),
                ("sync_state", models.CharField(choices=[("not_ready", "대기"), ("pending", "진행중"), ("success", "성공"), ("failed", "실패")], default="not_ready", max_length=20)),
                ("sync_error", models.TextField(blank=True)),
                ("synced_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="expenses.expensecategory")),
                ("paid_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="paid_expense_requests", to=settings.AUTH_USER_MODEL)),
                ("requester", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="expense_requests", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name": "지출 요청",
                "verbose_name_plural": "지출 요청",
            },
        ),
        migrations.CreateModel(
            name="SyncLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("service", models.CharField(choices=[("drive", "Google Drive"), ("sheets", "Google Sheets"), ("combined", "통합")], max_length=20)),
                ("status", models.CharField(choices=[("success", "성공"), ("failed", "실패"), ("skipped", "건너뜀")], max_length=20)),
                ("action", models.CharField(max_length=100)),
                ("message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sync_logs", to="expenses.expenserequest")),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name": "동기화 로그",
                "verbose_name_plural": "동기화 로그",
            },
        ),
        migrations.CreateModel(
            name="ExpenseStatusHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("from_status", models.CharField(blank=True, max_length=20)),
                ("to_status", models.CharField(choices=[("submitted", "제출됨"), ("under_review", "검토중"), ("approved", "승인"), ("rejected", "반려"), ("paid", "지급 완료")], max_length=20)),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("changed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="expense_status_changes", to=settings.AUTH_USER_MODEL)),
                ("request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="status_history", to="expenses.expenserequest")),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name": "지출 상태 이력",
                "verbose_name_plural": "지출 상태 이력",
            },
        ),
        migrations.CreateModel(
            name="ExpenseAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to="expense_attachments/")),
                ("original_filename", models.CharField(max_length=255)),
                ("mime_type", models.CharField(max_length=100)),
                ("file_size", models.PositiveIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="expenses.expenserequest")),
            ],
            options={
                "ordering": ["created_at"],
                "verbose_name": "지출 첨부파일",
                "verbose_name_plural": "지출 첨부파일",
            },
        ),
    ]
