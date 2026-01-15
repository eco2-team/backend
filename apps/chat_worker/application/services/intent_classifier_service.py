"""Intent Classifier Service - 순수 비즈니스 로직.

Port 의존 없이 순수 로직만 담당:
- 프롬프트 구성
- LLM 응답 파싱
- 신뢰도 계산
- 복잡도 판단

Clean Architecture:
- Service: 이 파일 (순수 로직, Port 의존 없음)
- Command: ClassifyIntentCommand (Port 호출, 오케스트레이션)
- Domain: Intent, ChatIntent (결과 VO)

참고 논문:
- arxiv:2304.11384 - Multi-Intent ICL
- arxiv:2411.14252 - Chain-of-Intent (CIKM '25)
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass

from pydantic import BaseModel, Field

from chat_worker.domain import ChatIntent, Intent, QueryComplexity

logger = logging.getLogger(__name__)


# ===== Structured Output 스키마 (Pydantic) =====


class MultiIntentDetectionSchema(BaseModel):
    """Multi-Intent 감지 결과 스키마 (Structured Output용)."""

    is_multi: bool = Field(description="복수 의도 여부")
    reason: str = Field(description="판단 근거")
    detected_categories: list[str] = Field(description="감지된 카테고리 목록")
    confidence: float = Field(ge=0.0, le=1.0, default=0.8, description="신뢰도")


class QueryDecompositionSchema(BaseModel):
    """Query Decomposition 결과 스키마 (Structured Output용)."""

    is_compound: bool = Field(description="복합 질문 여부")
    queries: list[str] = Field(description="분해된 쿼리 목록")


# ===== 상수 =====

# 복잡도 판단 키워드
COMPLEX_KEYWORDS = frozenset(["그리고", "또한", "차이", "비교", "여러", "같이", "둘 다"])

# Multi-Intent 후보 키워드 (Stage 1 사전 필터용)
MULTI_INTENT_CANDIDATE_KEYWORDS = frozenset(
    ["그리고", "또", "같이", "함께", "둘 다", "도", ",", "이랑", "랑", "하고"]
)

# 확실히 단일 Intent인 패턴 (Stage 1 빠른 통과)
SINGLE_INTENT_PATTERNS = [
    r"^.{1,12}$",  # 12자 이하 짧은 문장
    r"^(뭐야|뭐|어떻게|왜|어디)\??$",  # 단순 의문사
]

# 신뢰도 임계값
CONFIDENCE_THRESHOLD = 0.6

# 캐시 TTL (초)
INTENT_CACHE_TTL = 3600  # 1시간

# 캐시 키 프리픽스
INTENT_CACHE_PREFIX = "intent:"
MULTI_DETECT_CACHE_PREFIX = "multi_detect:"

# Intent Transition Boost (Chain-of-Intent 논문 적용)
INTENT_TRANSITION_BOOST: dict[Intent, dict[Intent, float]] = {
    Intent.WASTE: {
        Intent.LOCATION: 0.15,  # "버리고 싶은데 센터 어디야?"
        Intent.CHARACTER: 0.05,
    },
    Intent.GENERAL: {
        Intent.WASTE: 0.10,
        Intent.CHARACTER: 0.05,
        Intent.LOCATION: 0.08,
    },
    Intent.LOCATION: {
        Intent.WASTE: 0.10,
    },
    Intent.CHARACTER: {
        Intent.WASTE: 0.08,
    },
}


# ===== DTO =====


@dataclass
class MultiIntentDetection:
    """Multi-Intent 감지 결과."""

    is_multi: bool
    reason: str
    detected_categories: list[str]
    confidence: float = 0.8


@dataclass
class DecomposedQuery:
    """분해된 쿼리 결과."""

    is_compound: bool
    queries: list[str]
    original: str


@dataclass
class IntentClassificationResult:
    """Intent 분류 결과 (Service 반환용)."""

    intent: Intent
    confidence: float
    is_complex: bool

    def to_chat_intent(self) -> ChatIntent:
        """Domain Value Object로 변환."""
        return ChatIntent(
            intent=self.intent,
            complexity=QueryComplexity.from_bool(self.is_complex),
            confidence=self.confidence,
        )


@dataclass
class MultiIntentResult:
    """Multi-Intent 분류 결과."""

    intents: list[ChatIntent]
    decomposed_queries: list[str]
    is_multi: bool
    original_message: str


# ===== Service =====


class IntentClassifierService:
    """의도 분류 서비스 (순수 로직).

    Port 의존 없이 순수 비즈니스 로직만 담당:
    - 프롬프트 구성
    - LLM 응답 파싱
    - 신뢰도 계산
    - 복잡도 판단

    LLM 호출, 캐시 접근은 Command에서 담당.
    """

    def __init__(
        self,
        intent_prompt: str,
        decompose_prompt: str,
        multi_detect_prompt: str,
    ):
        """초기화.

        Args:
            intent_prompt: Intent 분류 프롬프트
            decompose_prompt: Query Decomposition 프롬프트
            multi_detect_prompt: Multi-Intent 감지 프롬프트
        """
        self._intent_prompt = intent_prompt
        self._decompose_prompt = decompose_prompt
        self._multi_detect_prompt = multi_detect_prompt

    # ===== 프롬프트 구성 (순수 로직) =====

    def get_intent_system_prompt(self) -> str:
        """Intent 분류 시스템 프롬프트 반환."""
        return self._intent_prompt

    def get_decompose_system_prompt(self) -> str:
        """Query Decomposition 시스템 프롬프트 반환."""
        return self._decompose_prompt

    def get_multi_detect_system_prompt(self) -> str:
        """Multi-Intent 감지 시스템 프롬프트 반환."""
        return self._multi_detect_prompt

    def build_prompt_with_context(
        self,
        message: str,
        context: dict | None = None,
    ) -> str:
        """대화 맥락을 포함한 프롬프트 구성.

        Args:
            message: 사용자 메시지
            context: 대화 맥락 (previous_intents 등)

        Returns:
            구성된 프롬프트
        """
        if not context:
            return message

        previous_intents = context.get("previous_intents", [])
        if previous_intents:
            intent_history = ", ".join(previous_intents[-3:])
            return f"[이전 대화 의도: {intent_history}]\n{message}"

        return message

    # ===== LLM 응답 파싱 (순수 로직) =====

    def parse_intent_response(
        self,
        llm_response: str,
        message: str,
        context: dict | None = None,
    ) -> IntentClassificationResult:
        """LLM 응답을 파싱하여 Intent 분류 결과 생성.

        Args:
            llm_response: LLM 응답
            message: 원본 메시지
            context: 대화 맥락

        Returns:
            IntentClassificationResult
        """
        intent_str = llm_response.strip().lower()
        intent, confidence = self._parse_intent_with_confidence(intent_str, message)

        # Intent Transition Boost (Chain-of-Intent 적용)
        if context:
            previous_intents = context.get("previous_intents", [])
            boost = self._adjust_confidence_by_transition(intent, previous_intents)
            confidence = min(1.0, confidence + boost)

        # 신뢰도 기반 Fallback
        if confidence < CONFIDENCE_THRESHOLD:
            logger.warning(
                f"Low confidence ({confidence:.2f}) for intent={intent_str}, "
                f"falling back to general"
            )
            intent = Intent.GENERAL

        # 복잡도 판단
        is_complex = self.is_complex_query(message)

        return IntentClassificationResult(
            intent=intent,
            confidence=confidence,
            is_complex=is_complex,
        )

    def _parse_intent_with_confidence(
        self,
        intent_str: str,
        message: str,
    ) -> tuple[Intent, float]:
        """Intent 파싱 및 신뢰도 계산."""
        intent = Intent.from_string(intent_str)
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
        """키워드 기반 신뢰도 보정."""
        confidence = base_confidence

        keyword_map = {
            Intent.WASTE: ["버려", "버리", "분리", "재활용", "쓰레기", "폐기"],
            Intent.CHARACTER: ["캐릭터", "얻", "모아", "컬렉션"],
            # LOCATION: 장소 검색 (카카오맵)
            Intent.LOCATION: [
                "어디",
                "근처",
                "가까",
                "센터",
                "위치",
                "샵",
                "제로웨이스트",
                "대형폐기물",
                "재활용센터",
                "수거",
            ],
            Intent.WEB_SEARCH: ["최신", "최근", "뉴스", "정책", "규제", "발표", "공지"],
            Intent.GENERAL: ["안녕", "뭐야", "왜", "어때"],
        }

        keywords = keyword_map.get(intent, [])
        matches = sum(1 for k in keywords if k in message)

        if matches > 0:
            confidence += min(0.2, matches * 0.1)
        elif intent != Intent.GENERAL:
            confidence -= 0.1

        return confidence

    def _adjust_confidence_by_transition(
        self,
        intent: Intent,
        previous_intents: list[str],
    ) -> float:
        """Intent 전이 확률 기반 신뢰도 부스트."""
        if not previous_intents:
            return 0.0

        try:
            last_intent = Intent.from_string(previous_intents[-1])
            transitions = INTENT_TRANSITION_BOOST.get(last_intent, {})
            boost = transitions.get(intent, 0.0)

            if boost > 0:
                logger.debug(
                    f"Transition boost: {last_intent.value} → {intent.value} = +{boost}"
                )

            return boost
        except ValueError:
            return 0.0

    # ===== Multi-Intent 관련 (순수 로직) =====

    def parse_multi_detect_response(self, llm_response: str) -> MultiIntentDetection:
        """Multi-Intent 감지 LLM 응답 파싱."""
        try:
            data = json.loads(llm_response)
            return MultiIntentDetection(
                is_multi=data.get("is_multi", False),
                reason=data.get("reason", ""),
                detected_categories=data.get("detected_categories", []),
                confidence=data.get("confidence", 0.8),
            )
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse multi-intent response: {llm_response}")
            return MultiIntentDetection(
                is_multi=False,
                reason="parsing_error",
                detected_categories=[],
                confidence=0.5,
            )

    def parse_decompose_response(
        self, llm_response: str, original: str
    ) -> DecomposedQuery:
        """Query Decomposition LLM 응답 파싱."""
        try:
            data = json.loads(llm_response)
            return DecomposedQuery(
                is_compound=data.get("is_compound", False),
                queries=data.get("queries", [original]),
                original=original,
            )
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse decompose response: {llm_response}")
            return DecomposedQuery(
                is_compound=False,
                queries=[original],
                original=original,
            )

    # ===== 판별 로직 (순수 로직) =====

    def is_complex_query(self, message: str) -> bool:
        """복잡도 판단."""
        for keyword in COMPLEX_KEYWORDS:
            if keyword in message:
                return True
        return len(message) > 100

    def has_multi_intent_keywords(self, message: str) -> bool:
        """Multi-Intent 후보 키워드 포함 여부."""
        return any(k in message for k in MULTI_INTENT_CANDIDATE_KEYWORDS)

    def is_definitely_single_intent(self, message: str) -> bool:
        """확실히 단일 Intent인지 판별."""
        return any(re.match(p, message) for p in SINGLE_INTENT_PATTERNS)

    def has_multi_intent(self, message: str) -> bool:
        """Multi-Intent 가능성 판별 (빠른 휴리스틱)."""
        if self.is_definitely_single_intent(message):
            return False
        return self.has_multi_intent_keywords(message)

    # ===== 캐시 키 생성 (순수 로직) =====

    def generate_cache_key(self, message: str) -> str:
        """Intent 캐시 키 생성."""
        content = message.strip().lower()
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:16]
        return f"{INTENT_CACHE_PREFIX}{hash_val}"

    def generate_multi_detect_cache_key(self, message: str) -> str:
        """Multi-Intent 감지 캐시 키 생성."""
        content = message.strip().lower()
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:16]
        return f"{MULTI_DETECT_CACHE_PREFIX}{hash_val}"


# ===== 상수 export =====

__all__ = [
    "IntentClassifierService",
    "IntentClassificationResult",
    "MultiIntentDetection",
    "DecomposedQuery",
    "MultiIntentResult",
    "MultiIntentDetectionSchema",
    "QueryDecompositionSchema",
    "CONFIDENCE_THRESHOLD",
    "INTENT_CACHE_TTL",
]
