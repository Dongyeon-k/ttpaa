from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.chatbot.forms import ConstitutionUploadForm
from apps.chatbot.models import ConstitutionChunk, ConstitutionDocument, ConstitutionPage
from services.openai_chatbot import ConstitutionChatService, _quote_matches_page_text, _tokenize
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

    def test_constitution_upload_form_accepts_supported_file_types(self):
        for filename, content_type in (
            ("rules.pdf", "application/pdf"),
            ("rules.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            ("rules.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ):
            upload = SimpleUploadedFile(filename, b"test", content_type=content_type)
            form = ConstitutionUploadForm(data={"version_label": "2026.04"}, files={"file": upload})
            self.assertTrue(form.is_valid(), form.errors)

    def test_constitution_upload_form_rejects_unsupported_file_type(self):
        upload = SimpleUploadedFile("rules.txt", b"test", content_type="text/plain")
        form = ConstitutionUploadForm(data={"version_label": "2026.04"}, files={"file": upload})
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)

    @patch("services.pdf_ingestion._extract_docx_pages", return_value=[(1, "Article 1 Purpose\nDOCX text.")])
    def test_constitution_docx_upload_and_indexing(self, mocked_extract):
        document = ConstitutionDocument.objects.create(
            version_label="2026.04",
            file=SimpleUploadedFile(
                "rules.docx",
                b"docx test",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            upload_filename="rules.docx",
            uploaded_by=self.admin,
        )
        index_constitution_document(document)
        document.refresh_from_db()
        self.assertEqual(document.index_status, ConstitutionDocument.STATUS_INDEXED)
        self.assertEqual(document.pages.count(), 1)
        self.assertIn("DOCX text.", document.pages.first().text)
        self.assertGreater(document.chunks.count(), 0)
        mocked_extract.assert_called_once_with(document)

    @patch("services.pdf_ingestion._extract_xlsx_pages", return_value=[(1, "[시트: 회칙]\nArticle 1\tXLSX text.")])
    def test_constitution_xlsx_upload_and_indexing(self, mocked_extract):
        document = ConstitutionDocument.objects.create(
            version_label="2026.04",
            file=SimpleUploadedFile(
                "rules.xlsx",
                b"xlsx test",
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            upload_filename="rules.xlsx",
            uploaded_by=self.admin,
        )
        index_constitution_document(document)
        document.refresh_from_db()
        self.assertEqual(document.index_status, ConstitutionDocument.STATUS_INDEXED)
        self.assertEqual(document.pages.count(), 1)
        self.assertIn("XLSX text.", document.pages.first().text)
        self.assertGreater(document.chunks.count(), 0)
        mocked_extract.assert_called_once_with(document)

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

    def test_docx_source_page_hides_pdf_preview(self):
        document = ConstitutionDocument.objects.create(
            version_label="2026.04",
            file=SimpleUploadedFile(
                "rules.docx",
                b"docx test",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            upload_filename="rules.docx",
            uploaded_by=self.admin,
            index_status=ConstitutionDocument.STATUS_INDEXED,
        )
        page = ConstitutionPage.objects.create(document=document, page_number=1, text="Article 1 Purpose")

        self.client.login(username="admin", password="pass12345")
        response = self.client.get(reverse("chatbot-source-page", args=[page.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "원본 파일 열기")
        self.assertNotContains(response, reverse("chatbot-source-page-image", args=[page.pk]))

        image_response = self.client.get(reverse("chatbot-source-page-image", args=[page.pk]))
        self.assertEqual(image_response.status_code, 404)

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

    def test_chatbot_tokenizes_latin_terms_with_korean_particles(self):
        self.assertIn("ttpaa", _tokenize("TTPAA가 뭐야?", drop_stopwords=True))
        self.assertNotIn("뭐야", _tokenize("TTPAA가 뭐야?", drop_stopwords=True))
        self.assertIn("동문회", _tokenize("동문회의 목적은 무엇인가요?", drop_stopwords=True))

    def test_chatbot_retrieves_chunk_for_latin_term_with_korean_particle(self):
        document = ConstitutionDocument.objects.create(
            version_label="2026.04",
            file=SimpleUploadedFile("rules.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
            upload_filename="rules.pdf",
            uploaded_by=self.admin,
            is_active=True,
            index_status=ConstitutionDocument.STATUS_INDEXED,
        )
        page = ConstitutionPage.objects.create(
            document=document,
            page_number=1,
            text=(
                '제1조 명칭\n본 회의 명칭은 "고려대학교 피아노 동아리 교우회" 로 한다.\n'
                '약칭으로는 "TTPAA" 로 표기한다.'
            ),
        )
        ConstitutionChunk.objects.create(
            document=document,
            page=page,
            page_number=1,
            chunk_index=1,
            heading="제1조 명칭",
            text=page.text,
        )

        _, chunks = ConstitutionChatService()._retrieve_chunks("TTPAA가 뭐야?")

        self.assertEqual([chunk.pk for chunk in chunks], [page.chunks.first().pk])

    @override_settings(LLM_PROVIDER="openai", OPENAI_API_KEY="test-key")
    def test_chatbot_uses_full_document_text_before_chunk_retrieval(self):
        document = ConstitutionDocument.objects.create(
            version_label="2026.04",
            file=SimpleUploadedFile("rules.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
            upload_filename="rules.pdf",
            uploaded_by=self.admin,
            is_active=True,
            index_status=ConstitutionDocument.STATUS_INDEXED,
        )
        page = ConstitutionPage.objects.create(
            document=document,
            page_number=1,
            text='제1조 명칭\n약칭으로는 "TTPAA" 로 표기한다.',
        )
        ConstitutionChunk.objects.create(
            document=document,
            page=page,
            page_number=1,
            chunk_index=1,
            heading="제1조 명칭",
            text=page.text,
        )

        with patch("services.openai_chatbot.ConstitutionChatService._call_openai") as mocked:
            mocked.return_value = {
                "supported": True,
                "answer": "회칙상 약칭은 TTPAA입니다.",
                "refusal_reason": "",
                "citations": [{"page": 1, "heading": "제1조 명칭", "quote": '약칭으로는 "TTPAA" 로 표기한다.'}],
            }
            result = ConstitutionChatService().answer_question(user=self.member, question="약어가 뭔가요?")

        self.assertTrue(result["supported"])
        sources = mocked.call_args.args[1]
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].text, page.text)

    def test_chatbot_validates_quote_with_normalized_whitespace(self):
        page_text = (
            '본 회의 명칭은 "고려대학교 피아노 동아리 교우회" 로 한다.\n'
            '\t\t\t영문으로는 "Talk Through Piano Alumni Association" 으로 한다.\n'
            '\t\t\t약칭으로는 "TTPAA" 로 표기한다.'
        )
        quote = (
            '본 회의 명칭은 "고려대학교 피아노 동아리 교우회" 로 한다. '
            '영문으로는 "Talk Through Piano Alumni Association" 으로 한다. '
            '약칭으로는 "TTPAA" 로 표기한다.'
        )

        self.assertTrue(_quote_matches_page_text(quote, page_text))

    @override_settings(LLM_PROVIDER="gemini", GEMINI_API_KEY="test-key", GEMINI_CHAT_MODEL="gemini-2.5-flash")
    def test_chatbot_routes_to_gemini_provider(self):
        document = ConstitutionDocument.objects.create(
            version_label="2026.04",
            file=SimpleUploadedFile("rules.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
            upload_filename="rules.pdf",
            uploaded_by=self.admin,
            is_active=True,
            index_status=ConstitutionDocument.STATUS_INDEXED,
        )
        page = ConstitutionPage.objects.create(document=document, page_number=1, text='약칭으로는 "TTPAA" 로 표기한다.')
        ConstitutionChunk.objects.create(
            document=document,
            page=page,
            page_number=1,
            chunk_index=1,
            heading="제1조 명칭",
            text=page.text,
        )

        with patch("services.openai_chatbot.ConstitutionChatService._create_gemini_client", return_value=object()):
            with patch("services.openai_chatbot.ConstitutionChatService._call_gemini") as mocked:
                mocked.return_value = {
                    "supported": True,
                    "answer": "회칙상 약칭은 TTPAA입니다.",
                    "refusal_reason": None,
                    "citations": [{"page": 1, "heading": "제1조 명칭", "quote": '약칭으로는 "TTPAA" 로 표기한다.'}],
                }
                result = ConstitutionChatService().answer_question(user=self.member, question="TTPAA가 뭐야?")

        self.assertTrue(result["supported"])
        self.assertEqual(result["refusal_reason"], "")
        mocked.assert_called_once()

    @override_settings(LLM_PROVIDER="gemini", GEMINI_API_KEY="")
    def test_chatbot_reports_missing_gemini_key(self):
        result = ConstitutionChatService().answer_question(user=self.member, question="TTPAA가 뭐야?")

        self.assertFalse(result["supported"])
        self.assertEqual(result["error_type"], "configuration")
        self.assertIn("GEMINI_API_KEY", result["refusal_reason"])

    @override_settings(LLM_PROVIDER="openai", OPENAI_API_KEY="test-key")
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
        self.assertNotContains(response, "출처 보기")

    @override_settings(LLM_PROVIDER="openai", OPENAI_API_KEY="test-key")
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
