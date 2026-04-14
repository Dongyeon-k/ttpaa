from __future__ import annotations

import logging
import re

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from pypdf import PdfReader

from apps.chatbot.models import ConstitutionChunk, ConstitutionDocument, ConstitutionPage

logger = logging.getLogger("ttpaa")

HEADING_PATTERN = re.compile(r"(제\s*\d+\s*[장조]|제\s*\d+\s*[장]|제\s*\d+\s*조|Chapter\s+\d+|Article\s+\d+)")


def _ocr_pdf_page(pdf_bytes: bytes, page_number: int) -> str:
    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("OCR Python dependencies are not installed. Run pip install -r requirements.txt.") from exc

    dpi = getattr(settings, "CONSTITUTION_OCR_DPI", 200)
    lang = getattr(settings, "CONSTITUTION_OCR_LANG", "kor+eng")
    zoom = dpi / 72

    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        page = pdf.load_page(page_number - 1)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        return (pytesseract.image_to_string(image, lang=lang) or "").strip()


def _split_chunks(text: str, chunk_size: int = 900) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs or [text]:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return chunks or [text]


def _extract_heading(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if HEADING_PATTERN.search(line):
            return line[:255]
    return ""


def index_constitution_document(document: ConstitutionDocument) -> ConstitutionDocument:
    logger.info("constitution_index_started document_id=%s", document.pk)
    document.index_status = ConstitutionDocument.STATUS_PENDING
    document.index_error = ""
    document.save(update_fields=["index_status", "index_error"])

    try:
        document.file.open("rb")
        reader = PdfReader(document.file)
        pdf_bytes = None
        extracted_pages = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            min_text_chars = getattr(settings, "CONSTITUTION_OCR_MIN_TEXT_CHARS", 20)
            if len(text) < min_text_chars and getattr(settings, "CONSTITUTION_OCR_ENABLED", True):
                if pdf_bytes is None:
                    document.file.seek(0)
                    pdf_bytes = document.file.read()
                try:
                    ocr_text = _ocr_pdf_page(pdf_bytes, page_number)
                except Exception:
                    if text:
                        logger.warning("constitution_ocr_fallback_failed document_id=%s page=%s", document.pk, page_number)
                        ocr_text = ""
                    else:
                        raise
                if len(ocr_text) > len(text):
                    text = ocr_text
            extracted_pages.append((page_number, text))

        total_text_length = sum(len(text) for _, text in extracted_pages)
        if not extracted_pages or total_text_length == 0:
            raise ValueError(
                "PDF에서 검색 가능한 텍스트를 추출하지 못했습니다. OCR로도 텍스트를 찾지 못했거나 OCR 설정을 사용할 수 없습니다."
            )

        with transaction.atomic():
            document.pages.all().delete()
            document.chunks.all().delete()
            for page_number, text in extracted_pages:
                page_obj = ConstitutionPage.objects.create(document=document, page_number=page_number, text=text)
                if not text:
                    continue
                heading = _extract_heading(text)
                for chunk_index, chunk_text in enumerate(_split_chunks(text), start=1):
                    if not chunk_text.strip():
                        continue
                    ConstitutionChunk.objects.create(
                        document=document,
                        page=page_obj,
                        page_number=page_number,
                        chunk_index=chunk_index,
                        heading=heading,
                        text=chunk_text,
                    )
        document.index_status = ConstitutionDocument.STATUS_INDEXED
        document.indexed_at = timezone.now()
        document.index_error = ""
        document.save(update_fields=["index_status", "indexed_at", "index_error"])
        logger.info("constitution_index_completed document_id=%s", document.pk)
        return document
    except Exception as exc:
        document.index_status = ConstitutionDocument.STATUS_FAILED
        document.index_error = str(exc)
        document.save(update_fields=["index_status", "index_error"])
        logger.exception("constitution_index_failed document_id=%s", document.pk)
        raise
