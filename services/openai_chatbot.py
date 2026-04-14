from __future__ import annotations

import json
import logging
import re
from collections import Counter

from django.conf import settings
from openai import APIConnectionError, APIStatusError, AuthenticationError, BadRequestError, NotFoundError, OpenAI

from apps.chatbot.models import ChatQueryLog, ConstitutionDocument, ConstitutionPage

logger = logging.getLogger("ttpaa")


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[0-9A-Za-z가-힣]{2,}", text.lower())


class ConstitutionChatService:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

    def _retrieve_chunks(self, question: str):
        document = ConstitutionDocument.objects.filter(is_active=True, index_status=ConstitutionDocument.STATUS_INDEXED).first()
        if not document:
            return document, []

        question_tokens = Counter(_tokenize(question))
        scored = []
        for chunk in document.chunks.select_related("page").exclude(text=""):
            chunk_tokens = Counter(_tokenize(chunk.text))
            overlap = sum((question_tokens & chunk_tokens).values())
            if question.strip() and question.strip() in chunk.text:
                overlap += 5
            if overlap > 0:
                scored.append((overlap, chunk))
        scored.sort(key=lambda item: (-item[0], item[1].page_number, item[1].chunk_index))
        return document, [chunk for _, chunk in scored[:5]]

    def _call_openai(self, question: str, chunks) -> dict:
        if not self.client:
            return {
                "supported": False,
                "answer": "",
                "refusal_reason": "OpenAI API 키가 설정되지 않아 답변을 생성할 수 없습니다. 관리자에게 .env의 OPENAI_API_KEY 설정을 요청해 주세요.",
                "error_type": "configuration",
                "citations": [],
            }

        source_block = "\n\n".join(
            f"[page={chunk.page_number} heading={chunk.heading or '-'}]\n{chunk.text}" for chunk in chunks
        )
        response = self.client.chat.completions.create(
            model=settings.OPENAI_CHAT_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 TTPAA 회칙 전용 검증 보조기입니다. "
                        "제공된 출처 텍스트만 사용해 JSON으로 답하십시오. "
                        "지원되지 않으면 supported=false 와 refusal_reason 를 반환하십시오. "
                        "supported=true 인 경우 citations 배열의 각 quote 는 출처 텍스트에 정확히 존재해야 하며 page 와 일치해야 합니다. "
                        "추측, 일반 상식, 불확실한 해석을 금지합니다."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"질문: {question}\n\n"
                        "반환 JSON 스키마:\n"
                        '{"supported": bool, "answer": str, "refusal_reason": str, '
                        '"citations": [{"page": int, "heading": str, "quote": str}]}\n\n'
                        f"출처:\n{source_block}"
                    ),
                },
            ],
        )
        return json.loads(response.choices[0].message.content)

    def _validate_result(self, document, result: dict) -> dict:
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
            if not page or not quote or quote not in page.text:
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
        document, chunks = self._retrieve_chunks(question)
        if not self.client:
            result = {
                "supported": False,
                "answer": "",
                "refusal_reason": "OpenAI API 키가 설정되지 않아 답변을 생성할 수 없습니다. 관리자에게 .env의 OPENAI_API_KEY 설정을 요청해 주세요.",
                "error_type": "configuration",
                "citations": [],
            }
        elif not document:
            result = {
                "supported": False,
                "answer": "",
                "refusal_reason": "인덱싱이 완료된 활성 회칙이 없습니다. 회칙 관리에서 PDF 업로드 또는 재인덱싱 상태를 확인해 주세요.",
                "error_type": "index",
                "citations": [],
            }
        elif not chunks:
            has_extracted_text = any(text.strip() for text in document.pages.values_list("text", flat=True))
            if not has_extracted_text:
                result = {
                    "supported": False,
                    "answer": "",
                    "refusal_reason": "PDF에서 검색 가능한 텍스트를 찾지 못했습니다. OCR로도 텍스트를 찾지 못했거나 OCR 설정을 사용할 수 없습니다.",
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
                result = self._call_openai(question, chunks)
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
                    "refusal_reason": "OpenAI 답변 생성 중 오류가 발생했습니다. API 키, 네트워크, 모델 설정을 확인해 주세요.",
                    "error_type": "connection",
                    "citations": [],
                }

        ChatQueryLog.objects.create(
            document=document,
            user=user,
            question=question,
            supported=result.get("supported", False),
            answer_text=result.get("answer", ""),
            refusal_reason=result.get("refusal_reason", ""),
            raw_response_json=json.dumps(result, ensure_ascii=False),
        )
        logger.info(
            "chatbot_query user=%s supported=%s reason=%s",
            getattr(user, "pk", None),
            result.get("supported", False),
            result.get("refusal_reason", ""),
        )
        return result
