from django.contrib import admin

from apps.expenses.models import ExpenseAttachment, ExpenseCategory, ExpenseRequest, ExpenseStatusHistory, SyncLog


class ExpenseAttachmentInline(admin.TabularInline):
    model = ExpenseAttachment
    extra = 0


class ExpenseStatusHistoryInline(admin.TabularInline):
    model = ExpenseStatusHistory
    extra = 0
    readonly_fields = ("from_status", "to_status", "changed_by", "note", "created_at")


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")


@admin.register(ExpenseRequest)
class ExpenseRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "requester", "category", "amount_krw", "current_status", "sync_state", "created_at")
    list_filter = ("current_status", "sync_state", "category", "created_at")
    search_fields = ("requester__username", "requester__first_name", "requester__email", "comment")
    inlines = [ExpenseAttachmentInline, ExpenseStatusHistoryInline]


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ("request", "service", "status", "action", "created_at")
    list_filter = ("service", "status", "created_at")
