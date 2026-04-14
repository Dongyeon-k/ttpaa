from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings
from django.db.models import Count
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import DetailView, TemplateView

from apps.chatbot.forms import ChatQuestionForm, ConstitutionUploadForm
from apps.chatbot.models import ConstitutionDocument, ConstitutionPage
from apps.core.permissions import AdminRequiredMixin
from services.openai_chatbot import ConstitutionChatService
from services.pdf_ingestion import get_constitution_file_extension, index_constitution_document


def get_active_document_status():
    document = (
        ConstitutionDocument.objects.filter(is_active=True)
        .annotate(page_count=Count("pages", distinct=True), chunk_count=Count("chunks", distinct=True))
        .first()
    )
    if document:
        page_texts = list(document.pages.values_list("text", flat=True))
        document.text_character_count = sum(len(text.strip()) for text in page_texts)
        document.empty_page_count = sum(1 for text in page_texts if not text.strip())
        document.non_empty_chunk_count = document.chunks.exclude(text="").count()
    return document


def get_suggested_questions(document):
    if not document:
        return []

    questions = []
    seen_headings = set()
    chunks_with_headings = document.chunks.exclude(heading="").order_by("page_number", "chunk_index")[:20]
    for chunk in chunks_with_headings:
        heading = chunk.heading.strip()
        if heading in seen_headings:
            continue
        seen_headings.add(heading)
        questions.append(f"{heading[:60]} 내용은 뭐야?")
        if len(questions) >= 4:
            break

    if len(questions) < 4:
        pages = document.pages.exclude(text="").order_by("page_number")[: 4 - len(questions)]
        for page in pages:
            questions.append(f"{page.page_number}페이지에 있는 내용을 요약해줘.")

    return questions


class ChatbotPageView(LoginRequiredMixin, TemplateView):
    template_name = "chatbot/chatbot.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_document = get_active_document_status()
        context["question_form"] = ChatQuestionForm()
        context["active_document"] = active_document
        context["openai_configured"] = bool(settings.OPENAI_API_KEY)
        context["suggested_questions"] = get_suggested_questions(active_document)
        context["chatbot_ready"] = bool(
            active_document
            and active_document.index_status == ConstitutionDocument.STATUS_INDEXED
            and active_document.non_empty_chunk_count
            and active_document.text_character_count
            and settings.OPENAI_API_KEY
        )
        return context

    def post(self, request, *args, **kwargs):
        form = ChatQuestionForm(request.POST)
        if not form.is_valid():
            return render(request, "chatbot/partials/chat_response.html", {"result": None, "error": "질문을 입력해 주세요."})
        service = ConstitutionChatService()
        result = service.answer_question(user=request.user, question=form.cleaned_data["question"])
        template = "chatbot/partials/chat_response.html" if request.headers.get("HX-Request") else "chatbot/chatbot.html"
        active_document = get_active_document_status()
        context = {
            "question_form": form,
            "result": result,
            "active_document": active_document,
            "openai_configured": bool(settings.OPENAI_API_KEY),
            "suggested_questions": get_suggested_questions(active_document),
            "chatbot_ready": bool(
                active_document
                and active_document.index_status == ConstitutionDocument.STATUS_INDEXED
                and active_document.non_empty_chunk_count
                and active_document.text_character_count
                and settings.OPENAI_API_KEY
            ),
        }
        return render(request, template, context)


class ConstitutionManageView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    template_name = "chatbot/manage.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        documents = list(ConstitutionDocument.objects.prefetch_related("pages", "chunks").all())
        for document in documents:
            page_texts = [page.text for page in document.pages.all()]
            document.page_count = len(page_texts)
            document.text_character_count = sum(len(text.strip()) for text in page_texts)
            document.empty_page_count = sum(1 for text in page_texts if not text.strip())
            document.non_empty_chunk_count = sum(1 for chunk in document.chunks.all() if chunk.text.strip())
        context["upload_form"] = kwargs.get("upload_form") or ConstitutionUploadForm()
        context["documents"] = documents
        context["active_document"] = ConstitutionDocument.objects.filter(is_active=True).first()
        return context

    def post(self, request, *args, **kwargs):
        form = ConstitutionUploadForm(request.POST, request.FILES)
        if form.is_valid():
            ConstitutionDocument.objects.update(is_active=False)
            document = form.save(commit=False)
            document.uploaded_by = request.user
            document.upload_filename = request.FILES["file"].name
            document.is_active = True
            document.index_status = ConstitutionDocument.STATUS_PENDING
            document.save()
            try:
                index_constitution_document(document)
                messages.success(request, "회칙 파일 업로드 및 인덱싱이 완료되었습니다.")
            except Exception as exc:
                messages.error(request, f"업로드는 되었지만 인덱싱에 실패했습니다: {exc}")
            return redirect("constitution-manage")
        return self.render_to_response(self.get_context_data(upload_form=form))


class ReindexConstitutionView(LoginRequiredMixin, AdminRequiredMixin, View):
    def post(self, request, pk: int):
        document = get_object_or_404(ConstitutionDocument, pk=pk)
        try:
            index_constitution_document(document)
            messages.success(request, "회칙 인덱싱을 다시 실행했습니다.")
        except Exception as exc:
            messages.error(request, f"인덱싱 실패: {exc}")
        return redirect("constitution-manage")


class ConstitutionRawDataView(LoginRequiredMixin, AdminRequiredMixin, DetailView):
    model = ConstitutionDocument
    template_name = "chatbot/raw_data.html"
    context_object_name = "document"

    def get_queryset(self):
        return ConstitutionDocument.objects.prefetch_related("pages", "chunks")


class ChatbotSourcePageView(LoginRequiredMixin, DetailView):
    model = ConstitutionPage
    template_name = "chatbot/source_page.html"
    context_object_name = "page"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = self.object
        is_pdf = get_constitution_file_extension(page.document.upload_filename or page.document.file.name) == ".pdf"
        context["is_pdf"] = is_pdf
        context["source_page_url"] = (
            f"{page.document.file.url}#page={page.page_number}" if is_pdf else page.document.file.url
        )
        return context


class ChatbotSourcePageImageView(LoginRequiredMixin, View):
    def get(self, request, pk: int):
        page = get_object_or_404(ConstitutionPage.objects.select_related("document"), pk=pk)
        if get_constitution_file_extension(page.document.upload_filename or page.document.file.name) != ".pdf":
            raise Http404("Page image preview is only available for PDF files.")
        try:
            import fitz

            page.document.file.open("rb")
            pdf_bytes = page.document.file.read()
            with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
                if page.page_number < 1 or page.page_number > pdf.page_count:
                    raise Http404("PDF page not found.")
                pdf_page = pdf.load_page(page.page_number - 1)
                pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
                return HttpResponse(pixmap.tobytes("png"), content_type="image/png")
        except Http404:
            raise
        except Exception as exc:
            raise Http404("PDF page image could not be rendered.") from exc
