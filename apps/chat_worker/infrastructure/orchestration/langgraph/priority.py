"""Priority Scheduling for LangGraph Channel Separation.

OS 스케줄링 알고리즘을 LangGraph 병렬 실행에 적용:
1. Priority Scheduling: 노드별 정적 우선순위
2. Aging: deadline 기반 동적 우선순위 조정
3. Deadline Scheduling: 서비스 타입별 SLA 기반 deadline

낮은 값 = 높은 우선순위 (UNIX nice 값과 유사)

References:
- SLA-driven timeouts: https://www.contentful.com/blog/the-two-friends-of-a-distributed-systems-engineer-timeouts-and-retries/
- Timeout strategies: https://www.geeksforgeeks.org/system-design/timeout-strategies-in-microservices-architecture/
"""

from __future__ import annotations

import time
from enum import IntEnum


class Priority(IntEnum):
    """우선순위 레벨.

    낮은 값 = 높은 우선순위 (0이 가장 높음)
    UNIX nice 값(-20~19)과 유사한 개념

    Examples:
        - CRITICAL: 필수 컨텍스트 (답변 생성에 반드시 필요)
        - HIGH: 주요 서비스 (gRPC, 검색)
        - NORMAL: 기본값
        - LOW: Enrichment (부가 정보)
        - BACKGROUND: 백그라운드 (로깅, 메트릭)
    """

    CRITICAL = 0
    HIGH = 25
    NORMAL = 50
    LOW = 75
    BACKGROUND = 100


# ============================================================
# Node Priority Mapping
# ============================================================

NODE_PRIORITY: dict[str, Priority] = {
    # Critical: 이 컨텍스트 없으면 답변 불가
    "waste_rag": Priority.CRITICAL,
    "bulk_waste": Priority.CRITICAL,
    "location": Priority.CRITICAL,
    "collection_point": Priority.CRITICAL,
    # High: 주요 응답 품질에 영향
    "character": Priority.HIGH,
    "general": Priority.HIGH,
    "web_search": Priority.HIGH,
    # Normal: 일반
    "recyclable_price": Priority.NORMAL,
    "image_generation": Priority.NORMAL,
    # Low: 있으면 좋지만 없어도 됨
    "weather": Priority.LOW,
}
"""노드별 정적 우선순위 매핑.

contracts.py NODE_OUTPUT_FIELDS와 일관되게 유지해야 함.
"""


# ============================================================
# Node Deadline Mapping (SLA-driven)
# ============================================================

NODE_DEADLINE_MS: dict[str, int] = {
    # LLM/Image Generation: 느리고 비용이 높은 작업
    # - 이미지 생성 API는 10-30초 소요 가능
    # - Retry 시 2배 timeout 허용해야 하므로 30s 기본값
    "image_generation": 30000,
    # gRPC Services (Internal): 내부 서비스, 빠른 응답 기대
    # - Character/Location은 gRPC 기반
    # - 네트워크 지연 + 처리 시간 = 3-5s
    "character": 5000,
    "location": 5000,
    # External APIs (Weather, Web Search): 외부 네트워크 의존
    # - 네트워크 왕복 + API 처리 = 8-10s
    # - DuckDuckGo/OpenWeatherMap 평균 응답시간 기반
    "weather": 8000,
    "web_search": 10000,
    # RAG/Vector Search: 벡터 검색 + reranking
    # - Qdrant 검색 + BM25 + reranking = 5-8s
    "waste_rag": 8000,
    # External APIs (Domain-specific):
    # - 대형폐기물 조회 (지자체 API)
    # - 수거함 위치 (KECO API)
    "bulk_waste": 8000,
    "collection_point": 8000,
    # Local/Cached Data: 빠른 응답
    # - 로컬 시세 데이터 조회
    "recyclable_price": 5000,
    # General LLM: 단순 LLM 호출
    "general": 10000,
}
"""노드별 SLA 기반 deadline (ms).

서비스 타입별 특성에 따른 timeout 설정:
- LLM/Image: 30s (느린 작업, retry 고려)
- External API: 8-10s (네트워크 지연)
- gRPC Internal: 5s (내부 서비스)
- Local Data: 5s (빠른 조회)

Aging 알고리즘에서 80% 경과 시 우선순위 부스트 시작.
예: deadline=10000ms → 8000ms 경과 시 부스트
"""


# ============================================================
# Aging Constants
# ============================================================

FALLBACK_PRIORITY_PENALTY = 15
"""Fallback 결과에 부여되는 우선순위 페널티.

원본 결과보다 낮은 우선순위를 갖도록 함.
예: CRITICAL(0) + 15 = 15 (여전히 HIGH보다 높음)
"""

AGING_THRESHOLD_RATIO = 0.8
"""Aging 부스트가 시작되는 deadline 비율.

예: deadline=5000ms, ratio=0.8 → 4000ms 경과 시 부스트 시작
"""

AGING_MAX_BOOST = 20
"""Aging으로 인한 최대 우선순위 부스트.

예: LOW(75) - 20 = 55 (HIGH 수준으로 상승)
"""


# ============================================================
# Aging Algorithm
# ============================================================


def calculate_effective_priority(
    base_priority: int,
    created_at: float,
    deadline_ms: int,
    is_fallback: bool = False,
) -> int:
    """유효 우선순위 계산 (Aging 적용).

    Aging 원칙:
    - 대기 시간이 길어질수록 우선순위 상승
    - deadline에 가까워질수록 더 급격히 상승

    Args:
        base_priority: 정적 우선순위 (Priority enum 값)
        created_at: 생성 시각 (timestamp)
        deadline_ms: 마감 시간 (ms)
        is_fallback: fallback 결과 여부

    Returns:
        조정된 우선순위 (0~100, 낮을수록 높은 우선순위)

    Examples:
        >>> # 정상 케이스 - 충분한 시간
        >>> calculate_effective_priority(50, time.time(), 5000, False)
        50

        >>> # Fallback 케이스 - 페널티 적용
        >>> calculate_effective_priority(0, time.time(), 5000, True)
        15

        >>> # Aging 케이스 - deadline 80% 초과
        >>> calculate_effective_priority(75, time.time() - 4.5, 5000, False)
        55  # 75 - 20 = 55 (최대 부스트)
    """
    priority = base_priority

    # Aging: deadline 80% 경과 시 우선순위 부스트
    elapsed_ms = (time.time() - created_at) * 1000
    deadline_ratio = elapsed_ms / deadline_ms if deadline_ms > 0 else 0

    if deadline_ratio > AGING_THRESHOLD_RATIO:
        # 부스트 계산: 80%~100% 구간에서 0~20 부스트
        boost_ratio = (deadline_ratio - AGING_THRESHOLD_RATIO) / (1 - AGING_THRESHOLD_RATIO)
        aging_boost = min(AGING_MAX_BOOST, int(boost_ratio * AGING_MAX_BOOST))
        priority -= aging_boost

    # Fallback penalty: 원본보다 낮은 우선순위
    if is_fallback:
        priority += FALLBACK_PRIORITY_PENALTY

    # 범위 제한: 0~100
    return max(0, min(100, priority))


def get_node_priority(node_name: str) -> Priority:
    """노드의 정적 우선순위 조회.

    Args:
        node_name: 노드 이름

    Returns:
        우선순위 (없으면 NORMAL)
    """
    return NODE_PRIORITY.get(node_name, Priority.NORMAL)


DEFAULT_DEADLINE_MS = 5000
"""기본 deadline (매핑에 없는 노드용)."""


def get_node_deadline(node_name: str) -> int:
    """노드의 SLA 기반 deadline 조회.

    Args:
        node_name: 노드 이름

    Returns:
        deadline (ms), 없으면 DEFAULT_DEADLINE_MS
    """
    return NODE_DEADLINE_MS.get(node_name, DEFAULT_DEADLINE_MS)


__all__ = [
    "AGING_MAX_BOOST",
    "AGING_THRESHOLD_RATIO",
    "DEFAULT_DEADLINE_MS",
    "FALLBACK_PRIORITY_PENALTY",
    "NODE_DEADLINE_MS",
    "NODE_PRIORITY",
    "Priority",
    "calculate_effective_priority",
    "get_node_deadline",
    "get_node_priority",
]
