"""Classify Intent Command.

의도 분류 UseCase.

Clean Architecture:
- Command(UseCase): 이 파일 - Port 호출, 오케스트레이션
- Service: IntentClassifierService - 순수 비즈니스 로직 (Port 의존 없음)
- Port: LLMClientPort, CachePort, PromptLoaderPort - 외부 의존
- Node(Adapter): intent_node.py - LangGraph glue

구조:
- Command: 캐시 조회/저장, LLM 호출, Service 호출, 오케스트레이션
- Service: 프롬프트 구성, LLM 응답 파싱, 신뢰도 계산, 복잡도 판단
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from chat_worker.application.services.intent_classifier_service import (
    INTENT_CACHE_TTL,
    IntentClassificationSchema,
    IntentClassifierService,
)
from chat_worker.domain import ChatIntent

if TYPE_CHECKING:
    from chat_worker.application.ports.cache import CachePort
    from chat_worker.application.ports.llm import LLMClientPort
    from chat_worker.application.ports.prompt_loader import PromptLoaderPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClassifyIntentInput:
    """Command 입력 DTO."""

    job_id: str
    message: str
    conversation_history: list[dict[str, Any]] | None = None
    previous_intents: list[str] | None = None  # Chain-of-Intent: 이전 intent 문자열 배열


@dataclass
class ClassifyIntentOutput:
    """Command 출력 DTO."""

    intent: str
    confidence: float
    is_complex: bool
    has_multi_intent: bool = False
    additional_intents: list[str] = field(default_factory=list)
    decomposed_queries: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)


class ClassifyIntentCommand:
    """의도 분류 Command (UseCase).

    Port 호출 + 오케스트레이션:
    1. 캐시 조회 (CachePort)
    2. LLM 호출 (LLMClientPort)
    3. Service 호출 (순수 로직)
    4. 캐시 저장 (CachePort)

    Port 주입:
    - llm: LLM 클라이언트
    - prompt_loader: 프롬프트 로더
    - cache: 캐시 Port (선택)
    """

    def __init__(
        self,
        llm: "LLMClientPort",
        prompt_loader: "PromptLoaderPort",
        cache: "CachePort | None" = None,
        enable_multi_intent: bool = True,
    ) -> None:
        """Command 초기화.

        Args:
            llm: LLM 클라이언트
            prompt_loader: 프롬프트 로더
            cache: 캐시 Port (선택)
            enable_multi_intent: Multi-Intent 처리 활성화 여부
        """
        self._llm = llm
        self._cache = cache
        self._enable_cache = cache is not None
        self._enable_multi_intent = enable_multi_intent

        # Service 생성 (프롬프트 로드 - Port 없이 문자열만 전달)
        self._service = IntentClassifierService(
            intent_prompt=prompt_loader.load("classification", "intent"),
            decompose_prompt=prompt_loader.load("classification", "decompose"),
            multi_detect_prompt=prompt_loader.load("classification", "multi_intent_detect"),
        )

    async def execute(self, input_dto: ClassifyIntentInput) -> ClassifyIntentOutput:
        """Command 실행.

        Args:
            input_dto: 입력 DTO

        Returns:
            출력 DTO
        """
        events: list[str] = []
        message = input_dto.message
        # Chain-of-Intent: previous_intents는 intent 문자열 배열 (예: ["waste", "location"])
        context = (
            {"previous_intents": input_dto.previous_intents} if input_dto.previous_intents else None
        )

        if self._enable_multi_intent:
            return await self._execute_multi_intent(input_dto, events)
        else:
            return await self._execute_single_intent(message, context, events)

    async def _execute_single_intent(
        self,
        message: str,
        context: dict | None,
        events: list[str],
    ) -> ClassifyIntentOutput:
        """단일 Intent 분류 실행.

        Model-Centric 접근: Structured Output으로 모델 판단 신뢰.
        """
        # 1. 캐시 조회 (Command에서 Port 호출)
        if self._enable_cache and context is None:
            cache_key = self._service.generate_cache_key(message)
            try:
                cached = await self._cache.get(cache_key)
                if cached:
                    logger.debug(f"Intent cache hit: {cache_key}")
                    events.append("cache_hit")
                    # 캐시된 결과 반환
                    return ClassifyIntentOutput(
                        intent=cached.get("intent", "general"),
                        confidence=cached.get("confidence", 1.0),
                        is_complex=cached.get("is_complex", False),
                        has_multi_intent=False,
                        additional_intents=[],
                        decomposed_queries=[message],
                        events=events,
                    )
            except Exception as e:
                logger.warning(f"Cache get failed: {e}")
                events.append("cache_error")

        # 2. 프롬프트 구성 (Service - 순수 로직)
        prompt = self._service.build_prompt_with_context(message, context)

        # 3. LLM Structured Output 호출 (Model-Centric)
        try:
            structured_result = await self._llm.generate_structured(
                prompt=prompt,
                response_schema=IntentClassificationSchema,
                system_prompt=self._service.get_intent_system_prompt(),
                max_tokens=150,  # reasoning 포함하므로 토큰 증가
                temperature=0.2,  # 약간의 유연성 허용
            )
            events.append("llm_structured_called")
        except Exception as e:
            logger.error(f"LLM structured call failed: {e}")
            events.append("llm_error")
            return ClassifyIntentOutput(
                intent="general",
                confidence=0.0,
                is_complex=False,
                events=events,
            )

        # 4. Structured 응답 파싱 (Service - Model-Centric)
        result = self._service.parse_structured_intent_response(structured_result, message, context)
        events.append("intent_classified")

        # 5. 캐시 저장 (Command에서 Port 호출)
        if self._enable_cache and context is None:
            try:
                cache_key = self._service.generate_cache_key(message)
                await self._cache.set(
                    cache_key,
                    {
                        "intent": result.intent.value,
                        "confidence": result.confidence,
                        "is_complex": result.is_complex,
                    },
                    ttl=INTENT_CACHE_TTL,
                )
                events.append("cache_saved")
            except Exception as e:
                logger.warning(f"Cache set failed: {e}")

        # Multi-Intent 가능성 체크 (Service - 순수 로직)
        has_multi_intent = self._service.has_multi_intent(message)

        logger.info(
            "Single intent classification completed (Model-Centric)",
            extra={
                "intent": result.intent.value,
                "confidence": result.confidence,
                "reasoning": structured_result.reasoning,
            },
        )

        return ClassifyIntentOutput(
            intent=result.intent.value,
            confidence=result.confidence,
            is_complex=result.is_complex,
            has_multi_intent=has_multi_intent,
            additional_intents=[],
            decomposed_queries=[message],
            events=events,
        )

    async def _execute_multi_intent(
        self,
        input_dto: ClassifyIntentInput,
        events: list[str],
    ) -> ClassifyIntentOutput:
        """Multi-Intent 분류 실행 (Two-Stage)."""
        message = input_dto.message

        # Stage 1: 빠른 규칙 기반 필터 (Service - 순수 로직)
        if self._service.is_definitely_single_intent(message):
            logger.debug(f"Stage 1: Definitely single intent: {message[:30]}")
            return await self._execute_single_intent(message, None, events)

        if not self._service.has_multi_intent_keywords(message):
            logger.debug(f"Stage 1: No multi-intent keywords: {message[:30]}")
            return await self._execute_single_intent(message, None, events)

        events.append("multi_intent_candidate")

        # Stage 2: LLM 기반 Multi-Intent 감지 (Command에서 Port 호출)
        try:
            detect_response = await self._llm.generate(
                prompt=message,
                system_prompt=self._service.get_multi_detect_system_prompt(),
                max_tokens=200,
                temperature=0.1,
            )
            events.append("multi_detect_llm_called")

            # 파싱 (Service - 순수 로직)
            detection = self._service.parse_multi_detect_response(detect_response)

            if not detection.is_multi:
                logger.debug(f"Stage 2: LLM says single intent: {detection.reason}")
                events.append("multi_detect_single")
                return await self._execute_single_intent(message, None, events)

            events.append("multi_intent_detected")

        except Exception as e:
            logger.warning(f"Multi-intent detection failed: {e}, falling back")
            events.append("multi_detect_error")
            return await self._execute_single_intent(message, None, events)

        # Stage 3: Query Decomposition (Command에서 Port 호출)
        try:
            decompose_response = await self._llm.generate(
                prompt=message,
                system_prompt=self._service.get_decompose_system_prompt(),
                max_tokens=300,
                temperature=0.1,
            )
            events.append("decompose_llm_called")

            # 파싱 (Service - 순수 로직)
            decomposed = self._service.parse_decompose_response(decompose_response, message)
            queries = decomposed.queries if decomposed.is_compound else [message]

        except Exception as e:
            logger.warning(f"Query decomposition failed: {e}")
            events.append("decompose_error")
            queries = [message]

        # Stage 4: 각 쿼리별 Intent 분류
        intents: list[ChatIntent] = []
        for query in queries:
            single_result = await self._execute_single_intent(query, None, [])
            chat_intent = ChatIntent.simple(
                single_result.intent,
                confidence=single_result.confidence,
            )
            intents.append(chat_intent)

        events.append("multi_intent_classification_completed")

        if not intents:
            return await self._execute_single_intent(message, None, events)

        primary = intents[0]
        additional = [i.intent.value for i in intents[1:]] if len(intents) > 1 else []

        logger.info(
            "Multi-intent classification completed",
            extra={
                "primary_intent": primary.intent.value,
                "has_multi_intent": len(intents) > 1,
                "additional_intents": additional,
            },
        )

        return ClassifyIntentOutput(
            intent=primary.intent.value,
            confidence=primary.confidence,
            is_complex=primary.is_complex,
            has_multi_intent=len(intents) > 1,
            additional_intents=additional,
            decomposed_queries=queries,
            events=events,
        )
