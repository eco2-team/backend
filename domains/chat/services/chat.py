from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

try:
    from openai import AsyncOpenAI  # type: ignore
    from openai.types import Response  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    AsyncOpenAI = None  # type: ignore
    Response = None  # type: ignore

from domains._shared.schemas.waste import WasteClassificationResult
from domains._shared.waste_pipeline import PipelineError, process_waste_classification
from domains.chat.schemas.chat import (
    ChatFeedback,
    ChatMessage,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSession,
)


DEFAULT_MODEL = "gpt-4o-mini"


class ChatService:
    def __init__(self) -> None:
        self.model = os.getenv("OPENAI_CHAT_MODEL", DEFAULT_MODEL)
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = AsyncOpenAI(api_key=api_key) if AsyncOpenAI and api_key else None

    async def send_message(self, payload: ChatMessageRequest) -> ChatMessageResponse:
        session_id = payload.session_id or str(uuid4())
        history = payload.history or []
        image_urls = [str(url) for url in (payload.image_urls or [])]

        if image_urls:
            try:
                pipeline_result = await self._run_image_pipeline(payload.message, image_urls)
            except PipelineError:
                pipeline_result = None
            else:
                message_text = (
                    pipeline_result.final_answer.get("user_answer")
                    or pipeline_result.final_answer.get("answer")
                    or self._fallback_answer(payload.message)
                )
                return ChatMessageResponse(
                    session_id=session_id,
                    message=message_text,
                    suggestions=self._default_suggestions(),
                    model="gpt-5-mini",
                    latency_ms=None,
                    pipeline_result=pipeline_result,
                )

        if not self.client:
            return ChatMessageResponse(
                session_id=session_id,
                message=self._fallback_answer(payload.message),
                suggestions=self._default_suggestions(),
                model=self.model,
                latency_ms=None,
            )

        start = time.perf_counter()
        openai_messages = self._build_messages(history, payload.message)
        try:
            response: Response = await self.client.responses.create(
                model=self.model,
                input=openai_messages,
                temperature=payload.temperature,
            )
            latency_ms = int((time.perf_counter() - start) * 1000)
            content = response.output[0].content[0].text  # type: ignore[index]
        except Exception:  # pragma: no cover - network errors
            content = self._fallback_answer(payload.message)
            latency_ms = None

        return ChatMessageResponse(
            session_id=session_id,
            message=content,
            suggestions=self._default_suggestions(),
            model=self.model,
            latency_ms=latency_ms,
        )

    async def get_session(self, session_id: str) -> Optional[ChatSession]:
        now = datetime.utcnow()
        return ChatSession(
            session_id=session_id,
            messages=[
                ChatMessage(role="user", content="예시 세션입니다.", timestamp=now),
                ChatMessage(
                    role="assistant",
                    content="실제 기록 저장소가 연결되면 이 내용이 교체됩니다.",
                    timestamp=now,
                ),
            ],
            created_at=now,
            updated_at=now,
            model=self.model,
        )

    async def delete_session(self, session_id: str) -> None:
        _ = session_id

    async def suggestions(self) -> dict:
        return {"suggestions": self._default_suggestions()}

    async def submit_feedback(self, payload: ChatFeedback) -> None:
        _ = payload

    async def metrics(self) -> dict:
        return {
            "active_sessions": 12,
            "avg_response_ms": 320,
            "feedback_positive_ratio": 0.92,
            "model": self.model,
        }

    def _build_messages(self, history: List[ChatMessage], current: str) -> list[dict]:
        system_prompt = {
            "role": "system",
            "content": (
                "You are EcoMate, an assistant that answers recycling and sustainability "
                "questions in Korean. Provide concise, practical answers."
            ),
        }
        converted_history = [{"role": msg.role, "content": msg.content} for msg in history[-6:]]
        converted_history.append({"role": "user", "content": current})
        return [system_prompt, *converted_history]

    def _fallback_answer(self, message: str) -> str:
        return (
            "GPT-4o Mini 연결이 설정되지 않아 기본 답변을 제공합니다. "
            "질문: {question} → 페트병은 세척 후 라벨과 뚜껑을 분리하여 배출해주세요."
        ).format(question=message)

    def _default_suggestions(self) -> list[str]:
        return [
            "투명 페트병은 어떻게 버리나요?",
            "종이팩과 종이는 어떻게 구분하나요?",
            "스티로폼 재활용 요령을 알려줘.",
        ]

    async def _run_image_pipeline(
        self,
        user_input: str,
        image_urls: list[str],
    ) -> WasteClassificationResult:
        result = await asyncio.to_thread(
            process_waste_classification,
            user_input,
            image_urls,
            save_result=False,
            verbose=False,
        )
        return WasteClassificationResult(**result)
