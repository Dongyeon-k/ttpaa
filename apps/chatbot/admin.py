from django.contrib import admin

from apps.chatbot.models import ChatQueryLog, ConstitutionChunk, ConstitutionDocument, ConstitutionPage


class ConstitutionPageInline(admin.TabularInline):
    model = ConstitutionPage
    extra = 0
    readonly_fields = ("page_number", "text")


@admin.register(ConstitutionDocument)
class ConstitutionDocumentAdmin(admin.ModelAdmin):
    list_display = ("version_label", "is_active", "index_status", "uploaded_at", "indexed_at")
    list_filter = ("is_active", "index_status")
    inlines = [ConstitutionPageInline]


@admin.register(ConstitutionChunk)
class ConstitutionChunkAdmin(admin.ModelAdmin):
    list_display = ("document", "page_number", "chunk_index", "heading")
    list_filter = ("document",)
    search_fields = ("text", "heading")


@admin.register(ChatQueryLog)
class ChatQueryLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "supported")
    list_filter = ("supported", "created_at")
    search_fields = ("question", "answer_text", "refusal_reason")
