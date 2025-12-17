from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from domains._shared.schemas.waste import WasteClassificationResult
from domains._shared.waste_pipeline import process_waste_classification
from domains._shared.waste_pipeline.answer import generate_answer
from domains._shared.waste_pipeline.rag import get_disposal_rules
from domains._shared.waste_pipeline.text import classify_text
from domains.chat.schemas.chat import ChatMessageRequest, ChatMessageResponse


logger = logging.getLogger(__name__)


class ChatService:
    async def send_message(
        self,
        payload: ChatMessageRequest,
    ) -> ChatMessageResponse:
        image_url = str(payload.image_url) if payload.image_url else None
        logger.info(
            "Chat message received",
            extra={"has_image": image_url is not None, "message_length": len(payload.message)},
        )
        try:
            pipeline_result = await self._run_pipeline(payload.message, image_url)
        except Exception:
            logger.exception("Pipeline execution failed; using fallback answer.")
            return ChatMessageResponse(user_answer=self._fallback_answer(payload.message))

        return ChatMessageResponse(
            user_answer=self._render_answer(pipeline_result, payload.message)
        )

    def _fallback_answer(self, message: str) -> str:
        return ("이미지가 인식되지 않았어요! 다시 시도해주세요.").format()

    async def _run_pipeline(
        self,
        user_input: str,
        image_url: str | None,
    ) -> WasteClassificationResult:
        if image_url:
            return await self._run_image_pipeline(user_input, image_url)
        return await self._run_text_pipeline(user_input)

    async def _run_image_pipeline(
        self,
        user_input: str,
        image_url: str,
    ) -> WasteClassificationResult:
        started_at = datetime.now(timezone.utc)
        logger.info(
            "Chat image pipeline started at %s (image_url=%s)",
            started_at.isoformat(),
            image_url,
        )
        success = False
        try:
            result = await asyncio.to_thread(
                process_waste_classification,
                user_input,
                image_url,
                save_result=False,
                verbose=False,
            )
            success = True
            return WasteClassificationResult(**result)
        finally:
            finished_at = datetime.now(timezone.utc)
            elapsed_ms = (finished_at - started_at).total_seconds() * 1000
            logger.info(
                "Chat image pipeline finished at %s (%.1f ms, success=%s)",
                finished_at.isoformat(),
                elapsed_ms,
                success,
            )

    async def _run_text_pipeline(self, user_input: str) -> WasteClassificationResult:
        started_at = datetime.now(timezone.utc)
        logger.info(
            "Chat text pipeline started at %s",
            started_at.isoformat(),
        )
        success = False
        try:
            result = await asyncio.to_thread(self._execute_text_pipeline, user_input)
            success = True
            return WasteClassificationResult(**result)
        finally:
            finished_at = datetime.now(timezone.utc)
            elapsed_ms = (finished_at - started_at).total_seconds() * 1000
            logger.info(
                "Chat text pipeline finished at %s (%.1f ms, success=%s)",
                finished_at.isoformat(),
                elapsed_ms,
                success,
            )

    @staticmethod
    def _execute_text_pipeline(user_input: str) -> dict:
        classification_result = classify_text(user_input, save_result=False)
        disposal_rules = get_disposal_rules(classification_result) or {}
        final_answer = generate_answer(
            classification_result,
            disposal_rules,
            save_result=False,
            pipeline_type="text",
        )
        return {
            "classification_result": classification_result,
            "disposal_rules": disposal_rules,
            "final_answer": final_answer,
        }

    def _render_answer(
        self,
        pipeline_result: WasteClassificationResult,
        original_message: str,
    ) -> str:
        final_answer = pipeline_result.final_answer or {}
        text = str(final_answer.get("user_answer") or "").strip()
        if text:
            return text
        return self._fallback_answer(original_message)
