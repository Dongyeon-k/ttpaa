from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_ADMIN = "admin"
    ROLE_MEMBER = "member"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "관리자"),
        (ROLE_MEMBER, "구성원"),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_MEMBER)

    class Meta:
        verbose_name = "사용자"
        verbose_name_plural = "사용자"

    @property
    def is_portal_admin(self) -> bool:
        return self.is_superuser or self.role == self.ROLE_ADMIN

    def save(self, *args, **kwargs):
        if self.role == self.ROLE_ADMIN and not self.is_superuser:
            self.is_staff = True
        super().save(*args, **kwargs)
