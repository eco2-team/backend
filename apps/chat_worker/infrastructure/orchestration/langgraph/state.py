"""LangGraph State Schema.

멀티턴 대화를 위한 상태 정의.
Channel Separation + Priority Scheduling으로 Send API 병렬 실행 안전.

아키텍처:
```
ChatState
├── Core Layer (Immutable)
│   ├── job_id, user_id, thread_id     # 메타데이터
│   └── message, image_url             # 입력
│
├── Intent Layer
│   ├── intent, intent_confidence      # 분류 결과
│   └── additional_intents             # Multi-Intent
│
├── Context Channels (Annotated Reducer)
│   ├── disposal_rules                 # waste_rag 노드
│   ├── bulk_waste_context             # bulk_waste 노드
│   ├── location_context               # location 노드
│   ├── collection_point_context       # collection_point 노드
│   ├── character_context              # character 노드
│   ├── weather_context                # weather 노드
│   ├── web_search_results             # web_search 노드
│   ├── recyclable_price_context       # recyclable_price 노드
│   ├── image_generation_context       # image_generation 노드
│   └── general_context                # general 노드
│
├── Aggregator Flags
│   ├── needs_fallback
│   └── missing_required_contexts
│
└── Output Layer
    ├── answer                         # 최종 응답
    └── messages                       # 대화 히스토리
```

OS Scheduling 알고리즘:
1. Priority Scheduling: 노드별 정적 우선순위
2. Preemptive Scheduling: 높은 우선순위가 낮은 것을 선점
3. Aging: deadline 기반 동적 우선순위 조정
4. Lamport Clock: sequence로 이벤트 순서 보장
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage

from .priority import Priority


# ============================================================
# Reducers
# ============================================================


def add_messages(
    existing: list[AnyMessage] | None,
    new: list[AnyMessage] | AnyMessage,
) -> list[AnyMessage]:
    """메시지 리스트 병합 Reducer.

    Args:
        existing: 기존 메시지 리스트
        new: 추가할 메시지 (단일 또는 리스트)

    Returns:
        병합된 메시지 리스트
    """
    if existing is None:
        existing = []

    if isinstance(new, list):
        return existing + new
    return existing + [new]


def priority_preemptive_reducer(
    existing: dict[str, Any] | None,
    new: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """선점형 우선순위 Reducer.

    Preemptive Scheduling 원칙:
    - 높은 우선순위(낮은 값)가 낮은 우선순위를 선점
    - 동일 우선순위는 Lamport Clock(sequence)으로 결정

    판단 순서:
    1. None 처리
    2. success 비교 (true가 false를 선점)
    3. priority 비교 (낮은 값이 높은 우선순위)
    4. sequence 비교 (큰 값이 최신)

    Args:
        existing: 현재 채널에 있는 값
        new: 새로 도착한 값

    Returns:
        선점된(승리한) 값

    Examples:
        >>> # success=True가 success=False를 선점
        >>> priority_preemptive_reducer(
        ...     {"success": False, "_priority": 0},
        ...     {"success": True, "_priority": 50},
        ... )
        {"success": True, "_priority": 50}

        >>> # 높은 우선순위(낮은 값)가 선점
        >>> priority_preemptive_reducer(
        ...     {"success": True, "_priority": 50},
        ...     {"success": True, "_priority": 0},
        ... )
        {"success": True, "_priority": 0}

        >>> # 동일 우선순위 → sequence 큰 것
        >>> priority_preemptive_reducer(
        ...     {"success": True, "_priority": 0, "_sequence": 1},
        ...     {"success": True, "_priority": 0, "_sequence": 2},
        ... )
        {"success": True, "_priority": 0, "_sequence": 2}
    """
    # None 처리
    if new is None:
        return existing
    if existing is None:
        return new

    # success 비교: true가 false를 선점
    new_success = new.get("success", True)
    existing_success = existing.get("success", True)

    if new_success and not existing_success:
        return new
    if existing_success and not new_success:
        return existing

    # priority 비교: 낮은 값 = 높은 우선순위
    existing_priority = existing.get("_priority", Priority.NORMAL)
    new_priority = new.get("_priority", Priority.NORMAL)

    if new_priority < existing_priority:
        return new  # 높은 우선순위가 선점
    if new_priority > existing_priority:
        return existing

    # 동일 priority → Lamport Clock(sequence)으로 결정
    existing_seq = existing.get("_sequence", 0)
    new_seq = new.get("_sequence", 0)

    return new if new_seq >= existing_seq else existing


# ============================================================
# ChatState Schema
# ============================================================


class ChatState(TypedDict, total=False):
    """Chat 파이프라인 상태.

    Channel Separation + Annotated Reducer로 Send API 병렬 실행 안전.
    OS Scheduling 알고리즘 적용으로 결정적(Deterministic) 병합 보장.

    계층 구조:
    - Core Layer: 메타데이터, 입력 (불변)
    - Intent Layer: 의도 분류 결과
    - Context Channels: 서브에이전트 결과 (Reducer 적용)
    - Output Layer: 최종 응답
    """

    # ==================== Core Layer (Immutable) ====================

    # Metadata
    job_id: str
    """작업 ID (이벤트 추적용)."""

    user_id: str
    """사용자 ID (SSE 라우팅용)."""

    thread_id: str
    """대화 스레드 ID (멀티턴 컨텍스트)."""

    # Input
    message: str
    """현재 사용자 메시지."""

    image_url: str | None
    """이미지 URL (Vision 분석용)."""

    conversation_history: list[dict[str, Any]]
    """대화 히스토리 (컨텍스트 제공용)."""

    # ==================== Intent Layer ====================

    intent: str
    """분류된 의도 (waste, character, location, etc.)."""

    intent_confidence: float
    """의도 분류 신뢰도 (0.0~1.0)."""

    is_complex: bool
    """복합 질문 여부."""

    has_multi_intent: bool
    """Multi-Intent 여부."""

    additional_intents: list[str]
    """추가 의도 목록 (Multi-Intent)."""

    intent_history: list[str]
    """의도 히스토리 (Chain-of-Intent)."""

    decomposed_queries: list[str]
    """분해된 질문 목록 (Multi-Intent)."""

    current_query: str
    """현재 처리 중인 질문."""

    # ==================== Vision Layer ====================

    classification_result: str | None
    """Vision 분류 결과."""

    has_image: bool
    """이미지 존재 여부."""

    # ==================== Context Channels (Annotated Reducer) ====================
    # 각 채널은 단일 노드만 write (contracts.py NODE_OUTPUT_FIELDS 참조)
    # priority_preemptive_reducer로 병렬 실행 시 결정적 병합

    disposal_rules: Annotated[dict[str, Any] | None, priority_preemptive_reducer]
    """waste_rag 노드 출력. RAG 분리배출 규정."""

    bulk_waste_context: Annotated[dict[str, Any] | None, priority_preemptive_reducer]
    """bulk_waste 노드 출력. 대형폐기물 정보."""

    location_context: Annotated[dict[str, Any] | None, priority_preemptive_reducer]
    """location 노드 출력. gRPC 위치 정보."""

    collection_point_context: Annotated[dict[str, Any] | None, priority_preemptive_reducer]
    """collection_point 노드 출력. KECO 수거함 위치."""

    character_context: Annotated[dict[str, Any] | None, priority_preemptive_reducer]
    """character 노드 출력. 캐릭터 페르소나."""

    weather_context: Annotated[dict[str, Any] | None, priority_preemptive_reducer]
    """weather 노드 출력. 날씨 정보."""

    web_search_results: Annotated[dict[str, Any] | None, priority_preemptive_reducer]
    """web_search 노드 출력. 웹 검색 결과."""

    recyclable_price_context: Annotated[dict[str, Any] | None, priority_preemptive_reducer]
    """recyclable_price 노드 출력. 재활용 시세 정보."""

    image_generation_context: Annotated[dict[str, Any] | None, priority_preemptive_reducer]
    """image_generation 노드 출력. 이미지 생성 결과."""

    general_context: Annotated[dict[str, Any] | None, priority_preemptive_reducer]
    """general 노드 출력. 일반 대화 컨텍스트."""

    # ==================== Aggregator Flags ====================

    needs_fallback: bool
    """필수 컨텍스트 누락 시 True."""

    missing_required_contexts: list[str]
    """누락된 필수 필드 목록."""

    # ==================== Legacy Fields (Backward Compatibility) ====================
    # TODO: Phase 2 완료 후 제거 가능

    query: str
    """현재 사용자 질문 (message와 동일, 레거시)."""

    evidence: list[dict[str, Any]]
    """RAG 검색 결과 (disposal_rules로 대체)."""

    character: dict[str, Any] | None
    """Character 응답 (character_context로 대체)."""

    location: dict[str, Any] | None
    """Location 응답 (location_context로 대체)."""

    web_results: list[dict[str, Any]]
    """Web Search 결과 (web_search_results로 대체)."""

    feedback: dict[str, Any]
    """RAG 품질 평가 결과."""

    fallback_reason: str | None
    """Fallback 발생 사유."""

    summary: str
    """압축된 이전 대화 요약."""

    context: dict[str, Any]
    """LLM 입력용 컨텍스트."""

    # ==================== Output Layer ====================

    answer: str
    """최종 생성된 응답."""

    messages: Annotated[list[AnyMessage], add_messages]
    """대화 히스토리 (Reducer로 누적)."""

    # ==================== RAG Feedback ====================

    rag_feedback: dict[str, Any]
    """RAG 품질 평가 결과."""

    rag_quality_score: float
    """RAG 품질 점수."""

    # ==================== Error Handling ====================

    subagent_error: str | None
    """서브에이전트 에러 메시지."""

    vision_error: str | None
    """Vision 처리 에러."""

    pipeline_failed: bool
    """파이프라인 실패 여부."""

    pipeline_error: str | None
    """파이프라인 에러 메시지."""

    # ==================== Image Generation ====================

    generated_image_url: str | None
    """생성된 이미지 URL."""

    image_description: str | None
    """이미지 설명."""

    image_generation_error: str | None
    """이미지 생성 에러."""

    # ==================== Web Search ====================

    web_search_query: str | None
    """웹 검색 쿼리."""

    web_search_error: str | None
    """웹 검색 에러."""

    # ==================== Location ====================

    location_skipped: bool
    """위치 처리 스킵 여부."""

    needs_location: bool
    """위치 정보 필요 여부."""


class LLMInputState(TypedDict):
    """LLM 입력용 압축된 상태.

    컨텍스트 압축 후 LLM에 전달되는 상태.
    전체 messages 대신 압축된 context 사용.
    """

    summarized_messages: list[AnyMessage]
    context: dict[str, Any]
    query: str
    evidence: list[dict[str, Any]]


__all__ = [
    "ChatState",
    "LLMInputState",
    "add_messages",
    "priority_preemptive_reducer",
]
