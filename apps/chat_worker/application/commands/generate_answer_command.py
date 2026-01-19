"""Generate Answer Command.

답변 생성 UseCase.

Clean Architecture:
- Command(UseCase): 이 파일 - Port 호출, 오케스트레이션
- Service: AnswerGeneratorService - 순수 비즈니스 로직 (Port 의존 없음)
- Port: LLMClientPort, CachePort, PromptBuilderPort - 외부 의존
- Node(Adapter): answer_node.py - LangGraph glue

구조:
- Command: 캐시 조회/저장, LLM 호출, Service 호출, 오케스트레이션
- Service: 컨텍스트 조합, 프롬프트 포매팅

P2: Multi-Intent Policy 조합 주입
P3: Answer 캐싱 (간단한 질문)
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncIterator

from chat_worker.application.dto.answer_context import AnswerContext
from chat_worker.application.services.answer_generator import AnswerGeneratorService

if TYPE_CHECKING:
    from chat_worker.application.ports.cache import CachePort
    from chat_worker.application.ports.llm import LLMClientPort
    from chat_worker.application.ports.prompt_builder import PromptBuilderPort

logger = logging.getLogger(__name__)

# Answer 캐시 설정
ANSWER_CACHE_TTL = 3600  # 1시간
CACHEABLE_INTENTS = frozenset({"general", "greeting"})

# 웹 검색 트리거 키워드 (GENERAL intent에서 네이티브 검색 활성화)
WEB_SEARCH_KEYWORDS = frozenset(
    {
        "최신",
        "최근",
        "뉴스",
        "정책",
        "규제",
        "발표",
        "공지",
        "2024",
        "2025",
        "2026",
        "올해",
        "작년",
        "지난달",
        "현재",
        "요즘",
        "트렌드",
        "업데이트",
    }
)


@dataclass(frozen=True)
class GenerateAnswerInput:
    """Command 입력 DTO."""

    job_id: str
    message: str
    intent: str
    additional_intents: list[str] = field(default_factory=list)
    has_multi_intent: bool = False
    classification: dict[str, Any] | None = None
    disposal_rules: dict[str, Any] | None = None
    character_context: dict[str, Any] | None = None
    location_context: dict[str, Any] | None = None
    web_search_results: dict[str, Any] | None = None
    recyclable_price_context: str | None = None  # 재활용자원 시세 (문자열)
    bulk_waste_context: str | None = None  # 대형폐기물 정보 (문자열)
    weather_context: str | None = None  # 날씨 기반 분리배출 팁 (문자열)
    collection_point_context: str | None = None  # 수거함 위치 정보 (문자열)
    # Multi-turn 대화 컨텍스트
    conversation_history: list[dict[str, str]] | None = None  # 최근 대화 히스토리
    conversation_summary: str | None = None  # 압축된 이전 대화 요약


@dataclass
class GenerateAnswerOutput:
    """Command 출력 DTO."""

    answer: str
    cache_hit: bool = False
    events: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PreparedPrompt:
    """프롬프트 준비 결과.

    LangGraph stream_mode="messages" 지원을 위해
    answer_node에서 직접 LLM 호출할 때 사용.
    """

    prompt: str
    system_prompt: str
    cache_key: str
    is_cacheable: bool
    cached_answer: str | None = None


class GenerateAnswerCommand:
    """답변 생성 Command (UseCase).

    Port 호출 + 오케스트레이션:
    1. 캐시 조회 (CachePort)
    2. 컨텍스트 구성 (Service - 순수 로직)
    3. 프롬프트 구성 (Service - 순수 로직)
    4. LLM 호출 (LLMClientPort)
    5. 캐시 저장 (CachePort)

    Port 주입:
    - llm: LLM 클라이언트
    - prompt_builder: 프롬프트 빌더 Port
    - cache: 캐시 Port (선택)
    """

    def __init__(
        self,
        llm: "LLMClientPort",
        prompt_builder: "PromptBuilderPort",
        cache: "CachePort | None" = None,
        service: AnswerGeneratorService | None = None,
    ) -> None:
        """Command 초기화.

        Args:
            llm: LLM 클라이언트
            prompt_builder: 프롬프트 빌더 Port
            cache: 캐시 Port (선택)
            service: 답변 생성 서비스 (선택, 테스트 주입용)
        """
        self._llm = llm
        self._prompt_builder = prompt_builder
        self._cache = cache
        self._service = service or AnswerGeneratorService()

    def _generate_cache_key(self, message: str, intent: str) -> str:
        """Answer 캐시 키 생성."""
        content = f"answer:{intent}:{message.strip().lower()}"
        return f"answer:{hashlib.sha256(content.encode()).hexdigest()[:16]}"

    def _is_cacheable(self, intent: str, context: AnswerContext) -> bool:
        """캐시 가능 여부 판단.

        조건:
        - general/greeting Intent만 캐시 (동적 데이터 없음)
        - RAG/Subagent 컨텍스트가 없는 경우만 캐시
        """
        if intent not in CACHEABLE_INTENTS:
            return False
        if context.has_context():
            return False
        return True

    def _build_context(self, input_dto: GenerateAnswerInput) -> AnswerContext:
        """AnswerContext 구성 (Service 사용)."""
        disposal_rules = None
        if input_dto.disposal_rules:
            disposal_rules = input_dto.disposal_rules.get("data")

        return self._service.create_context(
            classification=input_dto.classification,
            disposal_rules=disposal_rules,
            character_context=input_dto.character_context,
            location_context=input_dto.location_context,
            web_search_results=input_dto.web_search_results,
            recyclable_price_context=input_dto.recyclable_price_context,
            bulk_waste_context=input_dto.bulk_waste_context,
            weather_context=input_dto.weather_context,
            collection_point_context=input_dto.collection_point_context,
            user_input=input_dto.message,
            conversation_history=input_dto.conversation_history,
            conversation_summary=input_dto.conversation_summary,
        )

    def _build_system_prompt(self, input_dto: GenerateAnswerInput) -> str:
        """시스템 프롬프트 구성 (Multi-Intent 지원)."""
        if input_dto.has_multi_intent and input_dto.additional_intents:
            all_intents = [input_dto.intent] + list(input_dto.additional_intents)
            return self._prompt_builder.build_multi(all_intents)
        return self._prompt_builder.build(input_dto.intent)

    def _needs_web_search(self, message: str, intent: str) -> bool:
        """웹 검색 필요 여부 판단.

        GENERAL intent에서 실시간 정보가 필요한 질문인지 확인.

        Args:
            message: 사용자 메시지
            intent: 분류된 의도

        Returns:
            웹 검색 필요 여부
        """
        if intent != "general":
            return False

        message_lower = message.lower()
        return any(keyword in message_lower for keyword in WEB_SEARCH_KEYWORDS)

    async def prepare(self, input_dto: GenerateAnswerInput) -> PreparedPrompt:
        """프롬프트 준비 (캐시 확인 포함).

        LangGraph stream_mode="messages" 지원을 위해
        answer_node에서 직접 LLM 호출할 때 사용.

        Args:
            input_dto: 입력 DTO

        Returns:
            PreparedPrompt with cache status
        """
        # 1. 컨텍스트 구성 (Service - 순수 로직)
        context = self._build_context(input_dto)
        cache_key = self._generate_cache_key(input_dto.message, input_dto.intent)
        is_cacheable = self._cache is not None and self._is_cacheable(input_dto.intent, context)

        # 2. 캐시 확인 (Command에서 Port 호출)
        cached_answer = None
        if is_cacheable:
            try:
                cached_answer = await self._cache.get(cache_key)
                if cached_answer:
                    logger.info(
                        "Answer cache hit",
                        extra={"job_id": input_dto.job_id, "intent": input_dto.intent},
                    )
            except Exception as e:
                logger.warning(f"Answer cache get failed: {e}")

        # 3. 프롬프트 구성 (Service - 순수 로직)
        prompt = self._service.build_prompt(context)
        system_prompt = self._build_system_prompt(input_dto)

        if input_dto.has_multi_intent:
            logger.info(
                f"Built multi-intent prompt for intents="
                f"{[input_dto.intent] + list(input_dto.additional_intents)}"
            )

        return PreparedPrompt(
            prompt=prompt,
            system_prompt=system_prompt,
            cache_key=cache_key,
            is_cacheable=is_cacheable,
            cached_answer=cached_answer,
        )

    async def save_to_cache(self, cache_key: str, answer: str) -> None:
        """캐시에 답변 저장.

        Args:
            cache_key: 캐시 키
            answer: 저장할 답변
        """
        if self._cache is None:
            return

        try:
            await self._cache.set(cache_key, answer, ttl=ANSWER_CACHE_TTL)
            logger.debug(f"Answer cached: {cache_key}")
        except Exception as e:
            logger.warning(f"Answer cache set failed: {e}")

    async def execute(
        self,
        input_dto: GenerateAnswerInput,
    ) -> AsyncIterator[str]:
        """Command 실행 (스트리밍).

        Args:
            input_dto: 입력 DTO

        Yields:
            토큰 스트림
        """
        # 1. 컨텍스트 구성 (Service - 순수 로직)
        context = self._build_context(input_dto)
        cache_key = self._generate_cache_key(input_dto.message, input_dto.intent)
        is_cacheable = self._cache is not None and self._is_cacheable(input_dto.intent, context)

        # 2. 캐시 확인 (Command에서 Port 호출)
        if is_cacheable:
            try:
                cached_answer = await self._cache.get(cache_key)
                if cached_answer:
                    logger.info(
                        "Answer cache hit",
                        extra={"job_id": input_dto.job_id, "intent": input_dto.intent},
                    )
                    # 캐시된 답변을 토큰 단위로 yield
                    for char in cached_answer:
                        yield char
                    return
            except Exception as e:
                logger.warning(f"Answer cache get failed: {e}")

        # 3. 프롬프트 구성 (Service - 순수 로직)
        prompt = self._service.build_prompt(context)
        system_prompt = self._build_system_prompt(input_dto)

        if input_dto.has_multi_intent:
            logger.info(
                f"Built multi-intent prompt for intents="
                f"{[input_dto.intent] + list(input_dto.additional_intents)}"
            )

        # 4. LLM 호출 (Command에서 Port 호출 - 스트리밍)
        # GENERAL intent에서 웹 검색이 필요한 경우 네이티브 도구 사용
        use_web_search = self._needs_web_search(input_dto.message, input_dto.intent)

        answer_parts = []
        if use_web_search:
            logger.info(
                "Using native web_search tool",
                extra={"job_id": input_dto.job_id, "message": input_dto.message[:50]},
            )
            async for token in self._llm.generate_with_tools(
                prompt=prompt,
                tools=["web_search"],
                system_prompt=system_prompt,
            ):
                answer_parts.append(token)
                yield token
        else:
            async for token in self._llm.generate_stream(
                prompt=prompt,
                system_prompt=system_prompt,
            ):
                answer_parts.append(token)
                yield token

        # 5. 캐시 저장 (Command에서 Port 호출)
        if is_cacheable and answer_parts:
            answer = "".join(answer_parts)
            try:
                await self._cache.set(cache_key, answer, ttl=ANSWER_CACHE_TTL)
                logger.debug(f"Answer cached: {cache_key}")
            except Exception as e:
                logger.warning(f"Answer cache set failed: {e}")

    async def execute_full(
        self,
        input_dto: GenerateAnswerInput,
    ) -> GenerateAnswerOutput:
        """Command 실행 (전체 답변).

        스트리밍이 필요 없는 경우 사용.

        Args:
            input_dto: 입력 DTO

        Returns:
            출력 DTO
        """
        events: list[str] = []
        answer_parts = []
        cache_hit = False

        # 컨텍스트 구성 (Service - 순수 로직)
        context = self._build_context(input_dto)
        cache_key = self._generate_cache_key(input_dto.message, input_dto.intent)
        is_cacheable = self._cache is not None and self._is_cacheable(input_dto.intent, context)

        # 캐시 확인 (Command에서 Port 호출)
        if is_cacheable:
            try:
                cached_answer = await self._cache.get(cache_key)
                if cached_answer:
                    events.append("cache_hit")
                    return GenerateAnswerOutput(
                        answer=cached_answer,
                        cache_hit=True,
                        events=events,
                    )
            except Exception:
                events.append("cache_error")

        # LLM 호출 (Command에서 Port 호출)
        prompt = self._service.build_prompt(context)
        system_prompt = self._build_system_prompt(input_dto)

        # GENERAL intent에서 웹 검색이 필요한 경우 네이티브 도구 사용
        use_web_search = self._needs_web_search(input_dto.message, input_dto.intent)

        try:
            if use_web_search:
                events.append("web_search_used")
                async for token in self._llm.generate_with_tools(
                    prompt=prompt,
                    tools=["web_search"],
                    system_prompt=system_prompt,
                ):
                    answer_parts.append(token)
            else:
                async for token in self._llm.generate_stream(
                    prompt=prompt,
                    system_prompt=system_prompt,
                ):
                    answer_parts.append(token)
            events.append("llm_called")
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            events.append("llm_error")
            return GenerateAnswerOutput(
                answer="죄송해요, 답변을 생성하는 데 문제가 생겼어요.",
                cache_hit=False,
                events=events,
            )

        answer = "".join(answer_parts)
        events.append("answer_generated")

        # 캐시 저장 (Command에서 Port 호출)
        if is_cacheable and answer:
            try:
                await self._cache.set(cache_key, answer, ttl=ANSWER_CACHE_TTL)
                events.append("cache_saved")
            except Exception:
                events.append("cache_save_error")

        return GenerateAnswerOutput(
            answer=answer,
            cache_hit=cache_hit,
            events=events,
        )
