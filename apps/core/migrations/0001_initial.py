from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="NotificationLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(max_length=100)),
                ("channel", models.CharField(choices=[("email", "이메일")], default="email", max_length=20)),
                ("recipient", models.EmailField(max_length=254)),
                ("subject", models.CharField(max_length=255)),
                ("body", models.TextField()),
                ("related_label", models.CharField(blank=True, max_length=100)),
                ("related_object_id", models.CharField(blank=True, max_length=50)),
                ("success", models.BooleanField(default=False)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name": "알림 로그",
                "verbose_name_plural": "알림 로그",
            },
        )
    ]
