from __future__ import annotations

import asyncio
import logging
import os
from typing import List
from uuid import uuid4

try:
    from openai import AsyncOpenAI  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    AsyncOpenAI = None  # type: ignore

from domains._shared.schemas.waste import WasteClassificationResult
from domains._shared.waste_pipeline import PipelineError, process_waste_classification
from domains.chat.core.config import get_settings
from domains.chat.schemas.chat import ChatMessage, ChatMessageRequest, ChatMessageResponse
from domains.chat.services.session_store import ChatSessionStore


logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.1"


class ChatService:
    def __init__(self, session_store: ChatSessionStore | None = None) -> None:
        settings = get_settings()
        self.model = os.getenv("OPENAI_CHAT_MODEL", DEFAULT_MODEL)
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = AsyncOpenAI(api_key=api_key) if AsyncOpenAI and api_key else None
        self.session_store = session_store or ChatSessionStore(
            redis=None,
            ttl_seconds=settings.session_ttl_seconds,
            max_history=settings.session_history_limit,
        )

    async def send_message(
        self,
        payload: ChatMessageRequest,
        *,
        user_id: str,
    ) -> ChatMessageResponse:
        session_id = payload.session_id or str(uuid4())
        stored_history = await self.session_store.fetch_messages(user_id, session_id)
        history: List[ChatMessage] = list(stored_history)
        if len(history) > self.session_store.max_history:
            history = history[-self.session_store.max_history :]
        image_url = str(payload.image_url) if payload.image_url else None

        if image_url:
            try:
                pipeline_result = await self._run_image_pipeline(payload.message, image_url)
            except PipelineError:
                logger.exception("Image pipeline failed; falling back to text response.")
                pipeline_result = None
            else:
                message_text = (
                    pipeline_result.final_answer.get("user_answer")
                    or pipeline_result.final_answer.get("answer")
                    or self._fallback_answer(payload.message)
                )
                assistant_message = (
                    pipeline_result.final_answer.get("assistant_summary") or message_text
                )
                await self.session_store.append_messages(
                    user_id,
                    session_id,
                    [
                        ChatMessage(role="user", content=payload.message),
                        ChatMessage(role="assistant", content=assistant_message),
                    ],
                )
                return ChatMessageResponse(session_id=session_id, user_answer=message_text)

        if not self.client:
            fallback = self._fallback_answer(payload.message)
            response = ChatMessageResponse(session_id=session_id, user_answer=fallback)
            await self.session_store.append_messages(
                user_id,
                session_id,
                [
                    ChatMessage(role="user", content=payload.message),
                    ChatMessage(role="assistant", content=fallback),
                ],
            )
            logger.warning("ChatService fallback: OpenAI client missing.")
            return response

        openai_input = self._build_messages(history, payload.message)
        try:
            response = await self.client.responses.create(
                model=self.model,
                input=openai_input,
                temperature=payload.temperature,
            )
            content = response.output[0].content[0].text  # type: ignore[index]
            logger.debug("OpenAI response success for session %s", session_id)
        except Exception:  # pragma: no cover - network errors
            logger.exception("OpenAI responses.create failed; using fallback answer.")
            content = self._fallback_answer(payload.message)

        response_payload = ChatMessageResponse(session_id=session_id, user_answer=content)
        await self.session_store.append_messages(
            user_id,
            session_id,
            [
                ChatMessage(role="user", content=payload.message),
                ChatMessage(role="assistant", content=response_payload.user_answer),
            ],
        )
        return response_payload

    def _build_messages(self, history: List[ChatMessage], current: str) -> list[dict]:
        def _to_message(role: str, text: str) -> dict:
            return {
                "role": role,
                "content": [
                    {
                        "type": "input_text",
                        "text": text,
                    }
                ],
            }

        system_text = (
            "You are EcoMate, an assistant that answers recycling and sustainability "
            "questions in Korean. Provide concise, practical answers."
        )
        limit = getattr(self.session_store, "max_history", 6)
        converted_history = [_to_message(msg.role, msg.content) for msg in history[-limit:]]
        converted_history.append(_to_message("user", current))
        return [_to_message("system", system_text), *converted_history]

    def _fallback_answer(self, message: str) -> str:
        return (
            "모델 연결이 설정되지 않아 기본 답변을 제공합니다. "
            "질문: {question} → 페트병은 세척 후 라벨과 뚜껑을 분리하여 배출해주세요."
        ).format(question=message)

    async def _run_image_pipeline(
        self,
        user_input: str,
        image_url: str,
    ) -> WasteClassificationResult:
        result = await asyncio.to_thread(
            process_waste_classification,
            user_input,
            image_url,
            save_result=False,
            verbose=False,
        )
        return WasteClassificationResult(**result)
