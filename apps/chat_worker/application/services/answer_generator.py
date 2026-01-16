"""Answer Generator Service - 순수 비즈니스 로직.

Port 의존 없이 순수 로직만 담당:
- 컨텍스트 조합
- 프롬프트 포매팅

LLM 호출은 Command에서 담당.

Clean Architecture:
- Service: 이 파일 (순수 로직, Port 의존 없음)
- Command: GenerateAnswerCommand (Port 호출, 오케스트레이션)
- DTO: AnswerContext (dto/)
"""

from __future__ import annotations

import logging
from typing import Any

from chat_worker.application.dto.answer_context import AnswerContext

logger = logging.getLogger(__name__)


class AnswerGeneratorService:
    """답변 생성 서비스 (순수 로직).

    Port 의존 없이 순수 비즈니스 로직만 담당:
    - 컨텍스트 조합
    - 프롬프트 포매팅

    LLM 호출은 Command에서 담당.
    """

    def build_prompt(self, context: AnswerContext) -> str:
        """AnswerContext에서 LLM 프롬프트 생성.

        Args:
            context: 답변 컨텍스트

        Returns:
            LLM에 전달할 프롬프트
        """
        prompt = context.to_prompt_context()

        logger.debug(
            "Built answer prompt",
            extra={
                "has_classification": context.classification is not None,
                "has_disposal_rules": context.disposal_rules is not None,
                "has_character": context.character_context is not None,
                "has_location": context.location_context is not None,
                "has_web_search": context.web_search_results is not None,
                "has_recyclable_price": context.recyclable_price_context is not None,
                "has_bulk_waste": context.bulk_waste_context is not None,
                "has_weather": context.weather_context is not None,
                "has_collection_point": context.collection_point_context is not None,
                "has_conversation_history": context.conversation_history is not None,
                "has_conversation_summary": context.conversation_summary is not None,
                "conversation_turns": len(context.conversation_history) if context.conversation_history else 0,
                "prompt_length": len(prompt),
            },
        )

        return prompt

    @staticmethod
    def create_context(
        classification: dict[str, Any] | None = None,
        disposal_rules: dict[str, Any] | None = None,
        character_context: dict[str, Any] | None = None,
        location_context: dict[str, Any] | None = None,
        web_search_results: dict[str, Any] | None = None,
        recyclable_price_context: str | None = None,
        bulk_waste_context: str | None = None,
        weather_context: str | None = None,
        collection_point_context: str | None = None,
        user_input: str = "",
        conversation_history: list[dict[str, str]] | None = None,
        conversation_summary: str | None = None,
    ) -> AnswerContext:
        """AnswerContext 팩토리 메서드.

        Args:
            classification: 분류 결과
            disposal_rules: 폐기 규칙
            character_context: 캐릭터 컨텍스트
            location_context: 위치 컨텍스트
            web_search_results: 웹 검색 결과
            recyclable_price_context: 재활용자원 시세 컨텍스트 (문자열)
            bulk_waste_context: 대형폐기물 정보 컨텍스트 (문자열)
            weather_context: 날씨 기반 분리배출 팁 (문자열)
            collection_point_context: 수거함 위치 정보 (문자열)
            user_input: 사용자 입력
            conversation_history: 최근 대화 히스토리 (Multi-turn)
            conversation_summary: 압축된 이전 대화 요약 (Multi-turn)

        Returns:
            AnswerContext 인스턴스
        """
        return AnswerContext(
            classification=classification,
            disposal_rules=disposal_rules,
            character_context=character_context,
            location_context=location_context,
            web_search_results=web_search_results,
            recyclable_price_context=recyclable_price_context,
            bulk_waste_context=bulk_waste_context,
            weather_context=weather_context,
            collection_point_context=collection_point_context,
            user_input=user_input,
            conversation_history=conversation_history,
            conversation_summary=conversation_summary,
        )

    def validate_context(self, context: AnswerContext) -> bool:
        """컨텍스트 유효성 검증.

        Args:
            context: 검증할 컨텍스트

        Returns:
            유효 여부
        """
        # 최소한 user_input이 있어야 함
        return bool(context.user_input and context.user_input.strip())

    def should_use_streaming(self, context: AnswerContext) -> bool:
        """스트리밍 사용 여부 판단.

        긴 답변이 예상되는 경우 스트리밍 권장.

        Args:
            context: 답변 컨텍스트

        Returns:
            스트리밍 사용 권장 여부
        """
        # 컨텍스트가 많으면 스트리밍 권장
        if context.has_context():
            return True

        # 긴 입력이면 스트리밍 권장
        if len(context.user_input) > 50:
            return True

        return False
