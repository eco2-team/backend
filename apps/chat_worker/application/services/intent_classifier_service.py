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

from chat_worker.application.dto.intent_signals import IntentSignals
from chat_worker.domain import ChatIntent, Intent, QueryComplexity

logger = logging.getLogger(__name__)


# ===== Structured Output 스키마 (Pydantic) =====


class IntentClassificationSchema(BaseModel):
    """Intent 분류 결과 스키마 (Structured Output용).

    Model-Centric 접근: 키워드 의존 없이 모델의 의미론적 판단에 의존.
    """

    intent: str = Field(
        description="분류된 의도. 반드시 다음 중 하나: waste, character, location, bulk_waste, recyclable_price, collection_point, image_generation, general"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="모델의 판단 신뢰도 (0.0~1.0). 확실하면 0.9 이상, 애매하면 0.5~0.7",
    )
    reasoning: str = Field(
        description="이 의도로 분류한 이유를 한 문장으로 설명",
    )


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

# Chain-of-Intent 부스트 상한 (ADR P2 명시)
MAX_TRANSITION_BOOST = 0.15

# Chain-of-Intent 부스트 적용 조건: 이전 신뢰도가 이 값 이상이어야 부스트 적용
MIN_CONFIDENCE_FOR_BOOST = 0.7

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
        Intent.COLLECTION_POINT: 0.10,  # "어디서 버려?" → 수거함
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
    Intent.BULK_WASTE: {
        Intent.LOCATION: 0.12,  # 대형폐기물 → 센터 위치
        Intent.RECYCLABLE_PRICE: 0.08,  # 대형폐기물 → 시세
    },
    Intent.RECYCLABLE_PRICE: {
        Intent.LOCATION: 0.10,  # 시세 → 센터 위치
        Intent.COLLECTION_POINT: 0.08,
    },
    Intent.COLLECTION_POINT: {
        Intent.WASTE: 0.10,  # 수거함 → 분리배출 방법
        Intent.LOCATION: 0.08,
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
    signals: IntentSignals | None = None

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
            context: 대화 맥락 (previous_intents, conversation_history)

        Returns:
            구성된 프롬프트
        """
        if not context:
            return message

        parts: list[str] = []

        # 1. 이전 대화 내용 (멀티턴 맥락 파악에 핵심)
        conversation_history = context.get("conversation_history", [])
        if conversation_history:
            # 최근 3개 대화만 포함 (토큰 절약)
            recent_history = conversation_history[-3:]
            history_lines = []
            for turn in recent_history:
                role = turn.get("role", "unknown")
                content = turn.get("content", "")[:100]  # 길이 제한
                if role == "user":
                    history_lines.append(f"사용자: {content}")
                elif role == "assistant":
                    history_lines.append(f"어시스턴트: {content}")
            if history_lines:
                parts.append("[최근 대화]\n" + "\n".join(history_lines))

        # 2. 이전 의도 (Chain-of-Intent)
        previous_intents = context.get("previous_intents", [])
        if previous_intents:
            intent_history = ", ".join(previous_intents[-3:])
            parts.append(f"[이전 의도: {intent_history}]")

        # 3. 현재 메시지
        parts.append(f"[현재 메시지]\n{message}")

        return "\n\n".join(parts) if parts else message

    # ===== LLM 응답 파싱 (순수 로직) =====

    def parse_structured_intent_response(
        self,
        structured_result: IntentClassificationSchema,
        message: str,
        context: dict | None = None,
    ) -> IntentClassificationResult:
        """Structured Output 결과를 파싱하여 Intent 분류 결과 생성.

        Model-Centric 접근: 키워드 의존 없이 모델 판단 신뢰.
        Chain-of-Intent 전이 부스트만 적용.

        Args:
            structured_result: LLM Structured Output 결과
            message: 원본 메시지
            context: 대화 맥락

        Returns:
            IntentClassificationResult
        """
        intent = Intent.from_string(structured_result.intent)
        llm_confidence = structured_result.confidence

        logger.debug(
            "Model reasoning for intent=%s: %s",
            intent.value,
            structured_result.reasoning,
        )

        # Chain-of-Intent 전이 부스트만 적용 (키워드 부스트 제거)
        transition_boost = 0.0
        if context:
            previous_intents = context.get("previous_intents", [])
            last_confidence = context.get("last_confidence")
            transition_boost = self._adjust_confidence_by_transition(
                intent, previous_intents, last_confidence
            )

        # IntentSignals 생성 (키워드 부스트 = 0, 길이 페널티 = 0)
        signals = IntentSignals(
            llm_confidence=llm_confidence,
            keyword_boost=0.0,  # Model-Centric: 키워드 부스트 제거
            transition_boost=transition_boost,
            length_penalty=0.0,  # Model-Centric: 길이 페널티 제거
        )

        final_confidence = signals.final_confidence

        # 신뢰도 기반 Fallback (임계값 낮춤 - 모델 신뢰)
        if final_confidence < CONFIDENCE_THRESHOLD:
            logger.warning(
                "Low confidence (%.2f) for intent=%s, reasoning: %s",
                final_confidence,
                intent.value,
                structured_result.reasoning,
            )
            # Model-Centric: fallback하지 않고 모델 판단 유지
            # 단, 로깅으로 낮은 신뢰도 기록

        is_complex = self.is_complex_query(message)

        return IntentClassificationResult(
            intent=intent,
            confidence=final_confidence,
            is_complex=is_complex,
            signals=signals,
        )

    def parse_intent_response(
        self,
        llm_response: str,
        message: str,
        context: dict | None = None,
    ) -> IntentClassificationResult:
        """LLM 응답을 파싱하여 Intent 분류 결과 생성.

        레거시 호환용. 새 코드는 parse_structured_intent_response 사용 권장.

        Args:
            llm_response: LLM 응답
            message: 원본 메시지
            context: 대화 맥락

        Returns:
            IntentClassificationResult (signals 포함)
        """
        intent_str = llm_response.strip().lower()

        # 1. LLM 기본 신뢰도 계산
        intent, llm_confidence, length_penalty = self._parse_intent_with_signals(
            intent_str, message
        )

        # 2. 키워드 부스트 계산
        keyword_boost = self._calculate_keyword_boost(message, intent)

        # 3. Chain-of-Intent 전이 부스트 계산
        transition_boost = 0.0
        if context:
            previous_intents = context.get("previous_intents", [])
            last_confidence = context.get("last_confidence")  # P2: 이전 신뢰도 체크
            transition_boost = self._adjust_confidence_by_transition(
                intent, previous_intents, last_confidence
            )

        # 4. IntentSignals 생성
        signals = IntentSignals(
            llm_confidence=llm_confidence,
            keyword_boost=keyword_boost,
            transition_boost=transition_boost,
            length_penalty=length_penalty,
        )

        # 최종 신뢰도 (IntentSignals에서 계산)
        final_confidence = signals.final_confidence

        # 신뢰도 기반 Fallback
        if final_confidence < CONFIDENCE_THRESHOLD:
            logger.warning(
                "Low confidence (%.2f) for intent=%s, falling back to general. "
                "Signals: llm=%.2f, keyword=%.2f, transition=%.2f, length=%.2f",
                final_confidence,
                intent_str,
                llm_confidence,
                keyword_boost,
                transition_boost,
                length_penalty,
            )
            intent = Intent.GENERAL

        # 복잡도 판단
        is_complex = self.is_complex_query(message)

        return IntentClassificationResult(
            intent=intent,
            confidence=final_confidence,
            is_complex=is_complex,
            signals=signals,
        )

    def _parse_intent_with_signals(
        self,
        intent_str: str,
        message: str,
    ) -> tuple[Intent, float, float]:
        """Intent 파싱 및 개별 신호 계산.

        Args:
            intent_str: LLM 응답 문자열
            message: 사용자 메시지

        Returns:
            (intent, llm_confidence, length_penalty) 튜플
        """
        intent = Intent.from_string(intent_str)
        llm_confidence = 1.0
        length_penalty = 0.0

        # 규칙 1: LLM 응답이 정확히 매칭되지 않으면 감점
        if intent_str not in [i.value for i in Intent]:
            llm_confidence -= 0.3

        # 규칙 2: 메시지가 너무 짧으면 페널티
        if len(message) < 5:
            length_penalty = -0.2

        return intent, max(0.0, min(1.0, llm_confidence)), length_penalty

    def _calculate_keyword_boost(
        self,
        message: str,
        intent: Intent,
    ) -> float:
        """키워드 매칭 기반 부스트 계산.

        Args:
            message: 사용자 메시지
            intent: 분류된 의도

        Returns:
            키워드 부스트 값 (0.0 ~ 0.2, 또는 음수 페널티)
        """
        keyword_map = {
            Intent.WASTE: ["버려", "버리", "분리", "재활용", "쓰레기", "폐기"],
            Intent.CHARACTER: ["캐릭터", "얻", "모아", "컬렉션"],
            Intent.LOCATION: [
                "어디",
                "근처",
                "가까",
                "위치",
                "샵",
                "제로웨이스트",
                "재활용센터",
            ],
            Intent.BULK_WASTE: [
                "대형폐기물",
                "대형",
                "소파",
                "냉장고",
                "세탁기",
                "가구",
                "수수료",
                "신청",
                "가전",
                "매트리스",
                "침대",
            ],
            Intent.RECYCLABLE_PRICE: [
                "시세",
                "가격",
                "얼마",
                "고철",
                "폐지",
                "매입",
                "kg",
                "킬로",
            ],
            Intent.COLLECTION_POINT: [
                "수거함",
                "의류수거",
                "폐건전지",
                "폐형광등",
                "형광등",
                "건전지",
                "의류",
            ],
            Intent.IMAGE_GENERATION: [
                "이미지",
                "그림",
                "인포그래픽",
                "시각",
                "보여줘",
                "그려",
            ],
            Intent.GENERAL: [
                "안녕",
                "뭐야",
                "왜",
                "어때",
                # 웹 검색 키워드 (WEB_SEARCH → GENERAL 통합)
                "최신",
                "최근",
                "뉴스",
                "정책",
                "규제",
                "발표",
                "공지",
            ],
        }

        keywords = keyword_map.get(intent, [])
        matches = sum(1 for k in keywords if k in message)

        if matches > 0:
            return min(0.2, matches * 0.1)  # 최대 0.2
        elif intent != Intent.GENERAL:
            return -0.1  # 페널티
        return 0.0

    def _parse_intent_with_confidence(
        self,
        intent_str: str,
        message: str,
    ) -> tuple[Intent, float]:
        """Intent 파싱 및 신뢰도 계산 (레거시, 호환성 유지)."""
        intent, llm_conf, length_pen = self._parse_intent_with_signals(intent_str, message)
        keyword_boost = self._calculate_keyword_boost(message, intent)
        confidence = llm_conf + keyword_boost + length_pen
        return intent, max(0.0, min(1.0, confidence))

    def _adjust_confidence_by_keywords(
        self,
        message: str,
        intent: Intent,
        base_confidence: float,
    ) -> float:
        """키워드 기반 신뢰도 보정 (레거시, _calculate_keyword_boost 위임)."""
        boost = self._calculate_keyword_boost(message, intent)
        return base_confidence + boost

    def _adjust_confidence_by_transition(
        self,
        intent: Intent,
        previous_intents: list[str],
        last_confidence: float | None = None,
    ) -> float:
        """Intent 전이 확률 기반 신뢰도 부스트.

        ADR P2 요구사항:
        - MAX_TRANSITION_BOOST = 0.15 상한
        - last_confidence < MIN_CONFIDENCE_FOR_BOOST이면 부스트 미적용

        Args:
            intent: 현재 분류된 의도
            previous_intents: 이전 의도 문자열 리스트
            last_confidence: 이전 의도의 신뢰도 (None이면 체크 스킵)

        Returns:
            적용할 부스트 값 (0.0 ~ MAX_TRANSITION_BOOST)
        """
        if not previous_intents:
            return 0.0

        # 이전 신뢰도가 낮으면 부스트 미적용 (ADR P2)
        if last_confidence is not None and last_confidence < MIN_CONFIDENCE_FOR_BOOST:
            logger.debug(
                "Transition boost skipped: last_confidence=%.2f < %.2f",
                last_confidence,
                MIN_CONFIDENCE_FOR_BOOST,
            )
            return 0.0

        try:
            last_intent = Intent.from_string(previous_intents[-1])
            transitions = INTENT_TRANSITION_BOOST.get(last_intent, {})
            boost = transitions.get(intent, 0.0)

            # 명시적 상한 적용 (ADR P2)
            boost = min(MAX_TRANSITION_BOOST, boost)

            if boost > 0:
                logger.debug(
                    "Transition boost: %s → %s = +%.2f",
                    last_intent.value,
                    intent.value,
                    boost,
                )

            return boost
        except ValueError:
            return 0.0

    # ===== Multi-Intent 관련 (순수 로직) =====

    def _extract_json_from_response(self, response: str) -> str:
        """LLM 응답에서 JSON 부분만 추출.

        Markdown 코드 블록(```json ... ``` 또는 ``` ... ```)을 제거하고
        순수 JSON만 반환.

        Args:
            response: LLM 응답 문자열

        Returns:
            추출된 JSON 문자열
        """
        text = response.strip()

        # 1. ```json ... ``` 또는 ``` ... ``` 형태의 코드 블록 처리
        if text.startswith("```"):
            # 첫 번째 줄(```json 또는 ```) 제거
            lines = text.split("\n", 1)
            if len(lines) > 1:
                text = lines[1]
            else:
                # 한 줄짜리인 경우 ``` 제거
                text = text[3:]

            # 마지막 ``` 제거
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3]

            text = text.strip()

        # 2. JSON 객체 추출 (중괄호로 시작/끝나는 부분)
        # 응답에 추가 텍스트가 있을 경우를 대비
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            text = text[start_idx : end_idx + 1]

        return text

    def parse_multi_detect_response(self, llm_response: str) -> MultiIntentDetection:
        """Multi-Intent 감지 LLM 응답 파싱."""
        try:
            # markdown 코드 블록 제거 후 파싱
            cleaned_response = self._extract_json_from_response(llm_response)
            data = json.loads(cleaned_response)
            result = MultiIntentDetection(
                is_multi=data.get("is_multi", False),
                reason=data.get("reason", ""),
                detected_categories=data.get("detected_categories", []),
                confidence=data.get("confidence", 0.8),
            )
            if result.is_multi:
                logger.info(
                    "Multi-intent detected: categories=%s, confidence=%.2f",
                    result.detected_categories,
                    result.confidence,
                )
            return result
        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse multi-intent response: %s (error: %s)",
                llm_response[:200],
                str(e),
            )
            return MultiIntentDetection(
                is_multi=False,
                reason="parsing_error",
                detected_categories=[],
                confidence=0.5,
            )

    def parse_decompose_response(self, llm_response: str, original: str) -> DecomposedQuery:
        """Query Decomposition LLM 응답 파싱."""
        try:
            # markdown 코드 블록 제거 후 파싱
            cleaned_response = self._extract_json_from_response(llm_response)
            data = json.loads(cleaned_response)
            return DecomposedQuery(
                is_compound=data.get("is_compound", False),
                queries=data.get("queries", [original]),
                original=original,
            )
        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse decompose response: %s (error: %s)",
                llm_response[:200],
                str(e),
            )
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
    "IntentClassificationSchema",
    "MultiIntentDetection",
    "DecomposedQuery",
    "MultiIntentResult",
    "MultiIntentDetectionSchema",
    "QueryDecompositionSchema",
    "CONFIDENCE_THRESHOLD",
    "INTENT_CACHE_TTL",
    "MAX_TRANSITION_BOOST",
    "MIN_CONFIDENCE_FOR_BOOST",
]
