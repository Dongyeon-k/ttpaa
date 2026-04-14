from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ConstitutionDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version_label", models.CharField(max_length=100)),
                ("file", models.FileField(upload_to="constitutions/")),
                ("upload_filename", models.CharField(max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("index_status", models.CharField(choices=[("pending", "대기"), ("indexed", "인덱싱 완료"), ("failed", "실패")], default="pending", max_length=20)),
                ("index_error", models.TextField(blank=True)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("indexed_at", models.DateTimeField(blank=True, null=True)),
                ("uploaded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="uploaded_constitutions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-uploaded_at"],
                "verbose_name": "회칙 문서",
                "verbose_name_plural": "회칙 문서",
            },
        ),
        migrations.CreateModel(
            name="ChatQueryLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("question", models.TextField()),
                ("supported", models.BooleanField(default=False)),
                ("answer_text", models.TextField(blank=True)),
                ("refusal_reason", models.TextField(blank=True)),
                ("raw_response_json", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("document", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="chatbot.constitutiondocument")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name": "챗봇 질의 로그",
                "verbose_name_plural": "챗봇 질의 로그",
            },
        ),
        migrations.CreateModel(
            name="ConstitutionPage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("page_number", models.PositiveIntegerField()),
                ("text", models.TextField()),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pages", to="chatbot.constitutiondocument")),
            ],
            options={
                "ordering": ["page_number"],
                "verbose_name": "회칙 페이지",
                "verbose_name_plural": "회칙 페이지",
                "unique_together": {("document", "page_number")},
            },
        ),
        migrations.CreateModel(
            name="ConstitutionChunk",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("page_number", models.PositiveIntegerField()),
                ("chunk_index", models.PositiveIntegerField()),
                ("heading", models.CharField(blank=True, max_length=255)),
                ("text", models.TextField()),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chunks", to="chatbot.constitutiondocument")),
                ("page", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chunks", to="chatbot.constitutionpage")),
            ],
            options={
                "ordering": ["page_number", "chunk_index"],
                "verbose_name": "회칙 청크",
                "verbose_name_plural": "회칙 청크",
                "unique_together": {("document", "page_number", "chunk_index")},
            },
        ),
    ]
