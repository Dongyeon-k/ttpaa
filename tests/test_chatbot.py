from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.chatbot.models import ConstitutionChunk, ConstitutionDocument, ConstitutionPage
from services.pdf_ingestion import index_constitution_document


class FakePdfPage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class FakePdfReader:
    def __init__(self, *args, **kwargs):
        self.pages = [FakePdfPage("제1조 목적\n동문회의 목적은 친목 도모에 있다.")]


class EmptyPdfReader:
    def __init__(self, *args, **kwargs):
        self.pages = [FakePdfPage("")]


class ChatbotTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pass12345", role="admin")
        self.member = User.objects.create_user(username="member", password="pass12345", role="member")

    @patch("services.pdf_ingestion.PdfReader", FakePdfReader)
    def test_constitution_upload_and_indexing(self):
        document = ConstitutionDocument.objects.create(
            version_label="2026.04",
            file=SimpleUploadedFile("rules.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
            upload_filename="rules.pdf",
            uploaded_by=self.admin,
        )
        index_constitution_document(document)
        document.refresh_from_db()
        self.assertEqual(document.index_status, ConstitutionDocument.STATUS_INDEXED)
        self.assertEqual(document.pages.count(), 1)
        self.assertGreater(document.chunks.count(), 0)

    @override_settings(CONSTITUTION_OCR_ENABLED=False)
    @patch("services.pdf_ingestion.PdfReader", EmptyPdfReader)
    def test_constitution_indexing_fails_when_pdf_has_no_extractable_text(self):
        document = ConstitutionDocument.objects.create(
            version_label="2026.04",
            file=SimpleUploadedFile("rules.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
            upload_filename="rules.pdf",
            uploaded_by=self.admin,
        )
        with self.assertRaises(ValueError):
            index_constitution_document(document)
        document.refresh_from_db()
        self.assertEqual(document.index_status, ConstitutionDocument.STATUS_FAILED)
        self.assertIn("검색 가능한 텍스트", document.index_error)

    @patch("services.pdf_ingestion._ocr_pdf_page", return_value="Article 1 Purpose\nOCR extracted text.")
    @patch("services.pdf_ingestion.PdfReader", EmptyPdfReader)
    def test_constitution_indexing_uses_ocr_when_pdf_text_missing(self, mocked_ocr):
        document = ConstitutionDocument.objects.create(
            version_label="2026.04",
            file=SimpleUploadedFile("rules.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
            upload_filename="rules.pdf",
            uploaded_by=self.admin,
        )
        index_constitution_document(document)
        document.refresh_from_db()
        self.assertEqual(document.index_status, ConstitutionDocument.STATUS_INDEXED)
        self.assertEqual(document.pages.count(), 1)
        self.assertIn("OCR extracted text.", document.pages.first().text)
        self.assertGreater(document.chunks.count(), 0)
        mocked_ocr.assert_called_once()

    def test_admin_can_view_constitution_raw_data(self):
        document = ConstitutionDocument.objects.create(
            version_label="2026.04",
            file=SimpleUploadedFile("rules.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
            upload_filename="rules.pdf",
            uploaded_by=self.admin,
            index_status=ConstitutionDocument.STATUS_INDEXED,
        )
        page = ConstitutionPage.objects.create(document=document, page_number=1, text="Article 1 Purpose")
        ConstitutionChunk.objects.create(
            document=document,
            page=page,
            page_number=1,
            chunk_index=1,
            heading="Article 1",
            text="Article 1 Purpose",
        )

        self.client.login(username="admin", password="pass12345")
        response = self.client.get(reverse("constitution-raw-data", args=[document.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "페이지 원문")
        self.assertContains(response, "Article 1 Purpose")

    def test_member_nav_hides_admin_only_links(self):
        self.client.login(username="member", password="pass12345")
        response = self.client.get(reverse("chatbot"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "지출 요청")
        self.assertContains(response, "내 요청")
        self.assertContains(response, "회칙 챗봇")
        self.assertNotContains(response, "관리 검토")
        self.assertNotContains(response, "관리 설정")
        self.assertNotContains(response, "회칙 관리")

    def test_admin_nav_places_constitution_links_last_before_logout(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.get(reverse("chatbot"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        nav = content[content.index('<ul class="navbar-nav') : content.index("</ul>")]
        self.assertLess(nav.index("관리 검토"), nav.index("관리 설정"))
        self.assertLess(nav.index("관리 설정"), nav.index("회칙 관리"))
        self.assertLess(nav.index("회칙 관리"), nav.index("회칙 챗봇"))
        self.assertLess(nav.index("회칙 챗봇"), nav.index("로그아웃"))

    @override_settings(OPENAI_API_KEY="test-key")
    def test_chatbot_supported_answer_with_exact_quote(self):
        document = ConstitutionDocument.objects.create(
            version_label="2026.04",
            file=SimpleUploadedFile("rules.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
            upload_filename="rules.pdf",
            uploaded_by=self.admin,
            is_active=True,
            index_status=ConstitutionDocument.STATUS_INDEXED,
        )
        page = ConstitutionPage.objects.create(document=document, page_number=1, text="제1조 목적\n동문회의 목적은 친목 도모에 있다.")
        ConstitutionChunk.objects.create(document=document, page=page, page_number=1, chunk_index=1, heading="제1조 목적", text=page.text)

        self.client.login(username="member", password="pass12345")
        with patch("services.openai_chatbot.ConstitutionChatService._call_openai") as mocked:
            mocked.return_value = {
                "supported": True,
                "answer": "회칙상 동문회의 목적은 친목 도모입니다.",
                "refusal_reason": "",
                "citations": [{"page": 1, "heading": "제1조 목적", "quote": "동문회의 목적은 친목 도모에 있다."}],
            }
            response = self.client.post(reverse("chatbot"), {"question": "동문회의 목적은 무엇인가요?"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "회칙상 동문회의 목적은 친목 도모입니다.")
        self.assertContains(response, "페이지 1")

    @override_settings(OPENAI_API_KEY="test-key")
    def test_chatbot_refuses_when_unsupported(self):
        document = ConstitutionDocument.objects.create(
            version_label="2026.04",
            file=SimpleUploadedFile("rules.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
            upload_filename="rules.pdf",
            uploaded_by=self.admin,
            is_active=True,
            index_status=ConstitutionDocument.STATUS_INDEXED,
        )
        page = ConstitutionPage.objects.create(document=document, page_number=1, text="제1조 목적\n동문회의 목적은 친목 도모에 있다.")
        ConstitutionChunk.objects.create(document=document, page=page, page_number=1, chunk_index=1, heading="제1조 목적", text=page.text)

        self.client.login(username="member", password="pass12345")
        with patch("services.openai_chatbot.ConstitutionChatService._call_openai") as mocked:
            mocked.return_value = {
                "supported": False,
                "answer": "",
                "refusal_reason": "회칙에서 확인할 수 없습니다.",
                "citations": [],
            }
            response = self.client.post(reverse("chatbot"), {"question": "동문회의 목적은 무엇인가요?"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "회칙에서 확인할 수 없습니다.")
