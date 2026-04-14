from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.accounts.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("포털 설정", {"fields": ("role",)}),
    )
    list_display = ("username", "first_name", "email", "role", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff")
