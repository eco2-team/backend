"""Intent Classifier Service - 의도 분류 비즈니스 로직.

순수 비즈니스 로직만 포함. LangGraph 의존성 없음.
Domain Layer의 Intent, QueryComplexity, ChatIntent 사용.

Clean Architecture:
- Service: 비즈니스 로직 (이 파일)
- Port: LLMClientPort (generate만 사용)
- Domain: Intent, ChatIntent (결과 VO)

P0-P3 개선사항:
- P0: 프롬프트 파일 기반 로딩 (scan_worker 형식)
- P1: 신뢰도 기반 Fallback
- P2: Intent 캐싱 (Redis)
- P2: Multi-Intent 지원
- P3: 대화 맥락 활용
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from chat_worker.domain import ChatIntent, Intent, QueryComplexity

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from chat_worker.application.ports.llm import LLMClientPort

logger = logging.getLogger(__name__)

# 프롬프트 파일 경로
PROMPT_PATH = Path(__file__).parent.parent.parent.parent / (
    "infrastructure/assets/prompts/classification/intent.txt"
)

# 복잡도 판단 키워드
COMPLEX_KEYWORDS = frozenset(["그리고", "또한", "차이", "비교", "여러", "같이", "둘 다"])

# Multi-Intent 키워드
MULTI_INTENT_KEYWORDS = frozenset(["그리고", "또", "같이", "함께", "둘 다", "도"])

# 신뢰도 임계값
CONFIDENCE_THRESHOLD = 0.6

# 캐시 TTL (초)
INTENT_CACHE_TTL = 3600  # 1시간


@lru_cache(maxsize=1)
def _load_intent_prompt() -> str:
    """Intent 분류 프롬프트 로드 (LRU 캐싱)."""
    if not PROMPT_PATH.exists():
        logger.error(f"Intent prompt not found: {PROMPT_PATH}")
        raise FileNotFoundError(f"Intent prompt not found: {PROMPT_PATH}")

    content = PROMPT_PATH.read_text(encoding="utf-8")
    logger.debug(f"Loaded intent prompt ({len(content)} chars)")
    return content


class IntentClassifier:
    """의도 분류 서비스.

    책임:
    - 메시지 분석 → 의도 분류 (Domain: Intent)
    - 복잡도 판단 (Domain: QueryComplexity)
    - 신뢰도 계산 및 Fallback 처리
    - 결과 반환 (Domain: ChatIntent Value Object)

    LangGraph 노드에서 호출되며,
    노드는 이 서비스의 결과를 state에 반영하는 역할만 수행.
    """

    def __init__(
        self,
        llm: "LLMClientPort",
        redis: "Redis | None" = None,
        enable_cache: bool = True,
    ):
        """초기화.

        Args:
            llm: LLM 클라이언트
            redis: Redis 클라이언트 (캐싱용, 선택)
            enable_cache: 캐싱 활성화 여부
        """
        self._llm = llm
        self._redis = redis
        self._enable_cache = enable_cache and redis is not None
        self._prompt = _load_intent_prompt()

    async def classify(
        self,
        message: str,
        context: dict | None = None,
    ) -> ChatIntent:
        """메시지의 의도를 분류.

        Args:
            message: 사용자 메시지
            context: 대화 맥락 (P3: Checkpointer에서 제공)
                - previous_intents: 이전 대화의 Intent 목록
                - conversation_history: 최근 대화 히스토리

        Returns:
            ChatIntent: 불변 Value Object (Domain Layer)
        """
        # P2: 캐시 조회 (context 있으면 캐시 스킵 - 맥락 의존적)
        if self._enable_cache and context is None:
            cached = await self._get_cached_intent(message)
            if cached:
                logger.debug(f"Intent cache hit: {cached.intent.value}")
                return cached

        try:
            # P3: 대화 맥락 포함 프롬프트 생성
            prompt = self._build_prompt_with_context(message, context)

            # LLM 호출
            intent_str = await self._llm.generate(
                prompt=prompt,
                system_prompt=self._prompt,
                max_tokens=20,
                temperature=0.1,
            )

            # 정규화 및 신뢰도 계산
            intent_str = intent_str.strip().lower()
            intent, confidence = self._parse_intent_with_confidence(intent_str, message)

            # P1: 신뢰도 기반 Fallback
            if confidence < CONFIDENCE_THRESHOLD:
                logger.warning(
                    f"Low confidence ({confidence:.2f}) for intent={intent_str}, "
                    f"falling back to general"
                )
                intent = Intent.GENERAL

            # 복잡도 판단
            is_complex = self._is_complex_query(message)
            complexity = QueryComplexity.from_bool(is_complex)

            # P2: Multi-Intent 감지 (로깅만, 실제 처리는 P2에서)
            if self._has_multi_intent(message):
                logger.info(f"Multi-intent detected in message: {message[:50]}...")

            result = ChatIntent(
                intent=intent,
                complexity=complexity,
                confidence=confidence,
            )

            logger.info(
                "Intent classified",
                extra={
                    "intent": intent.value,
                    "complexity": complexity.value,
                    "confidence": confidence,
                },
            )

            # P2: 캐시 저장
            if self._enable_cache:
                await self._cache_intent(message, result)

            return result

        except Exception as e:
            logger.error("Intent classification failed: %s", e)
            return ChatIntent.simple_general(confidence=0.0)

    def _parse_intent_with_confidence(
        self,
        intent_str: str,
        message: str,
    ) -> tuple[Intent, float]:
        """Intent 파싱 및 신뢰도 계산.

        Args:
            intent_str: LLM 응답
            message: 원본 메시지

        Returns:
            (Intent, confidence) 튜플
        """
        # 기본 파싱
        intent = Intent.from_string(intent_str)

        # 신뢰도 계산 (규칙 기반)
        confidence = 1.0

        # 규칙 1: LLM 응답이 정확히 매칭되지 않으면 감점
        if intent_str not in [i.value for i in Intent]:
            confidence -= 0.3

        # 규칙 2: 메시지가 너무 짧으면 감점
        if len(message) < 5:
            confidence -= 0.2

        # 규칙 3: 키워드 매칭으로 보정
        confidence = self._adjust_confidence_by_keywords(message, intent, confidence)

        return intent, max(0.0, min(1.0, confidence))

    def _adjust_confidence_by_keywords(
        self,
        message: str,
        intent: Intent,
        base_confidence: float,
    ) -> float:
        """키워드 기반 신뢰도 보정.

        Args:
            message: 사용자 메시지
            intent: 분류된 Intent
            base_confidence: 기본 신뢰도

        Returns:
            보정된 신뢰도
        """
        confidence = base_confidence

        # Intent별 키워드 매칭
        keyword_map = {
            Intent.WASTE: ["버려", "버리", "분리", "재활용", "쓰레기", "폐기"],
            Intent.CHARACTER: ["캐릭터", "얻", "모아", "컬렉션"],
            Intent.LOCATION: ["어디", "근처", "가까", "센터", "위치", "샵"],
            Intent.WEB_SEARCH: ["최신", "최근", "뉴스", "정책", "규제", "발표", "공지"],
            Intent.GENERAL: ["안녕", "뭐야", "왜", "어때"],
        }

        keywords = keyword_map.get(intent, [])
        matches = sum(1 for k in keywords if k in message)

        if matches > 0:
            confidence += min(0.2, matches * 0.1)  # 최대 +0.2
        elif intent != Intent.GENERAL:
            confidence -= 0.1  # 키워드 없으면 감점

        return confidence

    def _is_complex_query(self, message: str) -> bool:
        """복잡도 판단."""
        for keyword in COMPLEX_KEYWORDS:
            if keyword in message:
                return True
        return len(message) > 100

    def _build_prompt_with_context(
        self,
        message: str,
        context: dict | None,
    ) -> str:
        """P3: 대화 맥락을 포함한 프롬프트 생성.

        Args:
            message: 현재 메시지
            context: 대화 맥락

        Returns:
            맥락이 포함된 프롬프트
        """
        if not context:
            return message

        parts = []

        # 이전 Intent 히스토리
        previous_intents = context.get("previous_intents", [])
        if previous_intents:
            recent_intents = previous_intents[-3:]  # 최근 3개만
            parts.append(f"[이전 대화 의도: {', '.join(recent_intents)}]")

        # 최근 대화 히스토리 (있으면)
        history = context.get("conversation_history", [])
        if history:
            recent = history[-2:]  # 최근 2턴만
            for turn in recent:
                if turn.get("role") == "user":
                    parts.append(f"[이전 질문: {turn.get('content', '')[:50]}...]")

        # 현재 메시지
        parts.append(f"[현재 질문: {message}]")

        prompt = "\n".join(parts)
        logger.debug(f"Context-aware prompt: {prompt[:100]}...")

        return prompt

    def _has_multi_intent(self, message: str) -> bool:
        """Multi-Intent 감지 (P2).

        "페트병 버리고 캐릭터도 알려줘" 같은 복합 질문 감지.
        """
        for keyword in MULTI_INTENT_KEYWORDS:
            if keyword in message:
                return True
        return False

    # ===== P2: 캐싱 =====

    async def _get_cached_intent(self, message: str) -> ChatIntent | None:
        """캐시에서 Intent 조회."""
        if not self._redis:
            return None

        try:
            import hashlib
            import json

            cache_key = f"intent:{hashlib.md5(message.encode()).hexdigest()}"
            cached = await self._redis.get(cache_key)

            if cached:
                data = json.loads(cached)
                return ChatIntent(
                    intent=Intent.from_string(data["intent"]),
                    complexity=QueryComplexity.from_string(data["complexity"]),
                    confidence=data["confidence"],
                )
        except Exception as e:
            logger.warning(f"Intent cache get failed: {e}")

        return None

    async def _cache_intent(self, message: str, result: ChatIntent) -> None:
        """Intent를 캐시에 저장."""
        if not self._redis:
            return

        try:
            import hashlib
            import json

            cache_key = f"intent:{hashlib.md5(message.encode()).hexdigest()}"
            data = json.dumps({
                "intent": result.intent.value,
                "complexity": result.complexity.value,
                "confidence": result.confidence,
            })
            await self._redis.setex(cache_key, INTENT_CACHE_TTL, data)
            logger.debug(f"Intent cached: {cache_key}")
        except Exception as e:
            logger.warning(f"Intent cache set failed: {e}")


# ===== P2: Multi-Intent Classifier (향후 확장) =====


class MultiIntentClassifier(IntentClassifier):
    """Multi-Intent 분류기 (P2 확장).

    "페트병 버리고 캐릭터도 알려줘" 같은 복합 질문을
    [waste, character]로 분류.
    """

    async def classify_multi(self, message: str) -> list[ChatIntent]:
        """복수 Intent 분류.

        Args:
            message: 사용자 메시지

        Returns:
            ChatIntent 리스트 (1~N개)
        """
        # 단일 Intent 우선
        primary = await self.classify(message)

        if not self._has_multi_intent(message):
            return [primary]

        # Multi-Intent 처리 (향후 구현)
        # TODO: LLM으로 복수 Intent 분류
        # TODO: 메시지 분할 및 개별 분류

        logger.info("Multi-intent detected, returning primary only (P2 TODO)")
        return [primary]
