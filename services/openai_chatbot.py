from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass

from django.conf import settings
from openai import APIConnectionError, APIStatusError, AuthenticationError, BadRequestError, NotFoundError, OpenAI

from apps.chatbot.models import ChatQueryLog, ConstitutionDocument, ConstitutionPage

logger = logging.getLogger("ttpaa")

SYSTEM_PROMPT = (
    "당신은 TTPAA 회칙 전용 검증 보조기입니다. "
    "제공된 출처 텍스트만 사용해 JSON으로 답하십시오. "
    "지원되지 않으면 supported=false 와 refusal_reason 를 반환하십시오. "
    "supported=true 인 경우 citations 배열의 각 quote 는 출처 텍스트에 정확히 존재해야 하며 page 와 일치해야 합니다. "
    "추측, 일반 상식, 불확실한 해석을 금지합니다."
)
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[가-힣]+")
KOREAN_PARTICLES = (
    "으로부터",
    "로부터",
    "으로는",
    "으로서",
    "으로써",
    "에게서",
    "한테서",
    "에서는",
    "에게",
    "한테",
    "에서",
    "으로",
    "라는",
    "이란",
    "란",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "의",
    "에",
    "와",
    "과",
    "로",
)
QUESTION_STOPWORDS = {
    "뭐야",
    "뭔가요",
    "뭔지",
    "무엇",
    "무엇인가",
    "무엇인가요",
    "알려줘",
    "알려주세요",
    "설명해줘",
    "설명해주세요",
    "내용",
}
FULL_TEXT_MAX_CHARS = 120_000


@dataclass(frozen=True)
class SourceSegment:
    page_number: int
    heading: str
    text: str


def _strip_korean_particle(token: str) -> str:
    for particle in KOREAN_PARTICLES:
        if token.endswith(particle) and len(token) - len(particle) >= 2:
            return token[: -len(particle)]
    return token


def _append_unique(tokens: list[str], seen: set[str], token: str, *, drop_stopwords: bool) -> None:
    if len(token) < 2 or token in seen:
        return
    if drop_stopwords and token in QUESTION_STOPWORDS:
        return
    tokens.append(token)
    seen.add(token)


def _tokenize(text: str, *, drop_stopwords: bool = False) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for raw_token in TOKEN_PATTERN.findall(text.lower()):
        _append_unique(tokens, seen, raw_token, drop_stopwords=drop_stopwords)
        if re.fullmatch(r"[가-힣]+", raw_token):
            _append_unique(tokens, seen, _strip_korean_particle(raw_token), drop_stopwords=drop_stopwords)
    return tokens


def _normalize_quote_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _quote_matches_page_text(quote: str, page_text: str) -> bool:
    return quote in page_text or _normalize_quote_text(quote) in _normalize_quote_text(page_text)


def _parse_json_response(text: str) -> dict:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _normalize_result(result: dict) -> dict:
    result["answer"] = result.get("answer") or ""
    result["refusal_reason"] = result.get("refusal_reason") or ""
    result["citations"] = result.get("citations") or []
    return result


class ConstitutionChatService:
    def __init__(self):
        self.provider = (getattr(settings, "LLM_PROVIDER", "openai") or "openai").lower()
        self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
        self.gemini_client = self._create_gemini_client() if self.provider == "gemini" else None

    def _create_gemini_client(self):
        if not settings.GEMINI_API_KEY:
            return None
        try:
            from google import genai
        except ImportError:
            logger.exception("gemini_sdk_missing")
            return None
        return genai.Client(api_key=settings.GEMINI_API_KEY)

    def _is_configured(self) -> bool:
        if self.provider == "openai":
            return bool(self.openai_client)
        if self.provider == "gemini":
            return bool(self.gemini_client)
        return False

    def _configuration_error(self) -> dict:
        if self.provider == "gemini":
            if not settings.GEMINI_API_KEY:
                message = "Gemini API 키가 설정되지 않아 답변을 생성할 수 없습니다. .env의 GEMINI_API_KEY를 설정해 주세요."
            else:
                message = "Gemini SDK를 사용할 수 없습니다. requirements 설치 후 컨테이너를 다시 빌드해 주세요."
        elif self.provider == "openai":
            message = "OpenAI API 키가 설정되지 않아 답변을 생성할 수 없습니다. 관리자에게 .env의 OPENAI_API_KEY 설정을 요청해 주세요."
        else:
            message = f"지원하지 않는 LLM_PROVIDER입니다: {self.provider}"
        return {
            "supported": False,
            "answer": "",
            "refusal_reason": message,
            "error_type": "configuration",
            "citations": [],
        }

    def _retrieve_chunks(self, question: str, document: ConstitutionDocument | None = None):
        document = document or ConstitutionDocument.objects.filter(
            is_active=True, index_status=ConstitutionDocument.STATUS_INDEXED
        ).first()
        if not document:
            return document, []

        question_tokens = Counter(_tokenize(question, drop_stopwords=True))
        scored = []
        for chunk in document.chunks.select_related("page").exclude(text=""):
            chunk_tokens = Counter(_tokenize(chunk.text))
            overlap = sum((question_tokens & chunk_tokens).values())
            chunk_text = chunk.text.lower()
            overlap += sum(2 for token in question_tokens if len(token) >= 3 and token in chunk_text)
            if question.strip() and question.strip() in chunk.text:
                overlap += 5
            if overlap > 0:
                scored.append((overlap, chunk))
        scored.sort(key=lambda item: (-item[0], item[1].page_number, item[1].chunk_index))
        return document, [chunk for _, chunk in scored[:5]]

    def _retrieve_sources(self, question: str):
        document = ConstitutionDocument.objects.filter(is_active=True, index_status=ConstitutionDocument.STATUS_INDEXED).first()
        if not document:
            return document, []

        page_sources = [
            SourceSegment(page_number=page.page_number, heading="", text=page.text.strip())
            for page in document.pages.exclude(text="").order_by("page_number")
            if page.text.strip()
        ]
        total_chars = sum(len(source.text) for source in page_sources)
        max_chars = getattr(settings, "CONSTITUTION_FULL_TEXT_MAX_CHARS", FULL_TEXT_MAX_CHARS)
        if total_chars and total_chars <= max_chars:
            return document, page_sources

        return self._retrieve_chunks(question, document=document)

    def _call_openai(self, question: str, sources) -> dict:
        if not self._is_configured():
            return self._configuration_error()

        source_block = "\n\n".join(
            f"[page={source.page_number} heading={source.heading or '-'}]\n{source.text}" for source in sources
        )
        if self.provider == "gemini":
            return self._call_gemini(question, source_block)
        return self._call_openai_api(question, source_block)

    def _build_user_prompt(self, question: str, source_block: str) -> str:
        return (
            f"질문: {question}\n\n"
            "반환 JSON 스키마:\n"
            '{"supported": bool, "answer": str, "refusal_reason": str, '
            '"citations": [{"page": int, "heading": str, "quote": str}]}\n\n'
            f"출처:\n{source_block}"
        )

    def _call_openai_api(self, question: str, source_block: str) -> dict:
        response = self.openai_client.chat.completions.create(
            model=settings.OPENAI_CHAT_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": self._build_user_prompt(question, source_block),
                },
            ],
        )
        return _parse_json_response(response.choices[0].message.content)

    def _call_gemini(self, question: str, source_block: str) -> dict:
        from google.genai import types

        config_kwargs = {
            "system_instruction": SYSTEM_PROMPT,
            "temperature": 0,
            "response_mime_type": "application/json",
        }
        if settings.GEMINI_THINKING_BUDGET >= 0:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=settings.GEMINI_THINKING_BUDGET)

        response = self.gemini_client.models.generate_content(
            model=settings.GEMINI_CHAT_MODEL,
            contents=self._build_user_prompt(question, source_block),
            config=types.GenerateContentConfig(**config_kwargs),
        )
        return _parse_json_response(response.text)

    def _validate_result(self, document, result: dict) -> dict:
        result = _normalize_result(result)
        if not result.get("supported"):
            return result
        citations = result.get("citations") or []
        if not citations:
            return {
                "supported": False,
                "answer": "",
                "refusal_reason": "인용 근거가 없어 회칙에서 확인할 수 없습니다.",
                "citations": [],
            }
        valid_citations = []
        for citation in citations:
            page_number = citation.get("page")
            quote = citation.get("quote", "")
            page = ConstitutionPage.objects.filter(document=document, page_number=page_number).first()
            if not page or not quote or not _quote_matches_page_text(quote, page.text):
                logger.warning("chatbot_validation_failed page=%s quote=%s", page_number, quote)
                return {
                    "supported": False,
                    "answer": "",
                    "refusal_reason": "인용 검증에 실패하여 회칙에서 확인할 수 없습니다.",
                    "citations": [],
                }
            valid_citations.append(
                {
                    "page": page_number,
                    "heading": citation.get("heading", ""),
                    "quote": quote,
                    "page_id": page.pk,
                }
            )
        result["citations"] = valid_citations
        return result

    def answer_question(self, *, user, question: str) -> dict:
        document, sources = self._retrieve_sources(question)
        if not self._is_configured():
            result = self._configuration_error()
        elif not document:
            result = {
                "supported": False,
                "answer": "",
                "refusal_reason": "인덱싱이 완료된 활성 회칙이 없습니다. 회칙 관리에서 파일 업로드 또는 재인덱싱 상태를 확인해 주세요.",
                "error_type": "index",
                "citations": [],
            }
        elif not sources:
            has_extracted_text = any(text.strip() for text in document.pages.values_list("text", flat=True))
            if not has_extracted_text:
                result = {
                    "supported": False,
                    "answer": "",
                    "refusal_reason": "회칙 파일에서 검색 가능한 텍스트를 찾지 못했습니다. 파일 내용을 확인해 주세요.",
                    "error_type": "index",
                    "citations": [],
                }
            else:
                result = {
                    "supported": False,
                    "answer": "",
                    "refusal_reason": "질문과 일치하는 회칙 조각을 찾지 못했습니다. 아래 예시처럼 회칙에 나온 조항명이나 핵심 단어를 포함해 다시 질문해 주세요.",
                    "error_type": "retrieval",
                    "citations": [],
                }
        else:
            try:
                result = self._call_openai(question, sources)
                result = self._validate_result(document, result)
            except AuthenticationError:
                logger.exception("chatbot_openai_authentication_failed")
                result = {
                    "supported": False,
                    "answer": "",
                    "refusal_reason": "OpenAI API 키가 올바르지 않습니다. .env의 OPENAI_API_KEY에 OpenAI 프로젝트 키를 설정해 주세요.",
                    "error_type": "configuration",
                    "citations": [],
                }
            except (BadRequestError, NotFoundError):
                logger.exception("chatbot_openai_model_failed model=%s", settings.OPENAI_CHAT_MODEL)
                result = {
                    "supported": False,
                    "answer": "",
                    "refusal_reason": f"OpenAI 모델 설정을 확인해 주세요. 현재 모델: {settings.OPENAI_CHAT_MODEL}",
                    "error_type": "configuration",
                    "citations": [],
                }
            except APIConnectionError:
                logger.exception("chatbot_openai_connection_failed")
                result = {
                    "supported": False,
                    "answer": "",
                    "refusal_reason": "OpenAI API에 연결하지 못했습니다. 네트워크 또는 방화벽 설정을 확인해 주세요.",
                    "error_type": "connection",
                    "citations": [],
                }
            except APIStatusError:
                logger.exception("chatbot_openai_status_failed")
                result = {
                    "supported": False,
                    "answer": "",
                    "refusal_reason": "OpenAI API가 오류를 반환했습니다. 잠시 후 다시 시도하거나 API 상태와 사용량 한도를 확인해 주세요.",
                    "error_type": "connection",
                    "citations": [],
                }
            except Exception:
                logger.exception("chatbot_query_failed")
                result = {
                    "supported": False,
                    "answer": "",
                    "refusal_reason": "답변 생성 중 오류가 발생했습니다. API 키, 네트워크, 모델 설정을 확인해 주세요.",
                    "error_type": "connection",
                    "citations": [],
                }

        ChatQueryLog.objects.create(
            document=document,
            user=user,
            question=question,
            supported=result.get("supported", False),
            answer_text=result.get("answer") or "",
            refusal_reason=result.get("refusal_reason") or "",
            raw_response_json=json.dumps(result, ensure_ascii=False),
        )
        logger.info(
            "chatbot_query user=%s supported=%s reason=%s",
            getattr(user, "pk", None),
            result.get("supported", False),
            result.get("refusal_reason", ""),
        )
        return result
