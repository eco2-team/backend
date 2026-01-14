"""Answer Generator Service - 답변 생성 비즈니스 로직.

LLM을 사용한 답변 생성을 담당합니다.
컨텍스트 구성, 프롬프트 포매팅 등 비즈니스 로직 포함.

Clean Architecture:
- Service: 비즈니스 로직 (이 파일)
- Port: LLMClientPort (generate, generate_stream만 사용)
- DTO: AnswerContext (answer/dto/)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from chat_worker.application.answer.dto import AnswerContext

if TYPE_CHECKING:
    from chat_worker.application.ports.llm import LLMClientPort

logger = logging.getLogger(__name__)


class AnswerGeneratorService:
    """답변 생성 서비스.

    책임:
    - 컨텍스트 조합
    - 프롬프트 포매팅
    - LLM 호출 (Port 사용)
    - 스트리밍/일반 생성 지원

    LangGraph 노드에서 호출되며,
    노드는 이 서비스의 결과를 state에 반영하는 역할만 수행.
    """

    def __init__(self, llm: "LLMClientPort"):
        self._llm = llm

    async def generate(
        self,
        context: AnswerContext,
        system_prompt: str,
    ) -> str:
        """답변 생성 (일반)."""
        prompt = context.to_prompt_context()

        logger.debug(
            "Generating answer",
            extra={
                "has_classification": context.classification is not None,
                "has_disposal_rules": context.disposal_rules is not None,
                "has_character": context.character_context is not None,
                "has_location": context.location_context is not None,
            },
        )

        answer = await self._llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
        )

        logger.info("Answer generated", extra={"length": len(answer)})
        return answer

    async def generate_stream(
        self,
        context: AnswerContext,
        system_prompt: str,
    ) -> AsyncIterator[str]:
        """답변 생성 (스트리밍)."""
        prompt = context.to_prompt_context()

        logger.debug(
            "Generating answer (stream)",
            extra={
                "has_classification": context.classification is not None,
                "has_disposal_rules": context.disposal_rules is not None,
                "has_character": context.character_context is not None,
                "has_location": context.location_context is not None,
            },
        )

        async for chunk in self._llm.generate_stream(
            prompt=prompt,
            system_prompt=system_prompt,
        ):
            yield chunk

    @staticmethod
    def create_context(
        classification: dict[str, Any] | None = None,
        disposal_rules: dict[str, Any] | None = None,
        character_context: dict[str, Any] | None = None,
        location_context: dict[str, Any] | None = None,
        user_input: str = "",
    ) -> AnswerContext:
        """컨텍스트 팩토리 메서드."""
        return AnswerContext(
            classification=classification,
            disposal_rules=disposal_rules,
            character_context=character_context,
            location_context=location_context,
            user_input=user_input,
        )
