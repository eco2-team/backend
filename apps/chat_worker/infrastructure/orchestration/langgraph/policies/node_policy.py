"""Node Policy - 노드별 실행 정책 테이블.

각 노드의 timeout, retry, circuit breaker, fail mode를 정의합니다.

ADR 문서: docs/plans/chat-worker-production-architecture-adr.md

왜 NodePolicy가 필요한가?
1. 일관성: 모든 노드의 실행 정책을 한 곳에서 관리
2. 투명성: 각 설정의 근거를 명시적으로 문서화
3. 튜닝: 실제 측정 데이터 기반 조정 용이
"""

from __future__ import annotations

from dataclasses import dataclass

from chat_worker.domain.enums import FailMode


@dataclass(frozen=True)
class NodePolicy:
    """노드 실행 정책.

    Attributes:
        name: 노드 이름
        timeout_ms: 타임아웃 (밀리초)
        max_retries: 최대 재시도 횟수
        cb_threshold: Circuit Breaker 임계값 (연속 실패 횟수)
        fail_mode: 실패 처리 모드
        is_required: 필수 컨텍스트 여부
        rationale: 설정 근거 (디버깅/면접용)
    """

    name: str
    timeout_ms: int
    max_retries: int
    cb_threshold: int
    fail_mode: FailMode
    is_required: bool
    rationale: str = ""

    @property
    def timeout_seconds(self) -> float:
        """타임아웃 (초)."""
        return self.timeout_ms / 1000.0


# ADR 검증 완료: 실제 클라이언트 설정 기반
# 각 근거는 실제 측정 또는 SDK 기본값에서 도출
NODE_POLICIES: dict[str, NodePolicy] = {
    # 필수 노드 (FAIL_FALLBACK/CLOSE)
    "waste_rag": NodePolicy(
        name="waste_rag",
        timeout_ms=1000,
        max_retries=1,
        cb_threshold=5,
        fail_mode=FailMode.FAIL_FALLBACK,
        is_required=True,
        rationale="로컬 파일 검색 1초 이내, 실패 시 LLM 직접 응답",
    ),
    "bulk_waste": NodePolicy(
        name="bulk_waste",
        timeout_ms=10000,
        max_retries=2,
        cb_threshold=5,
        fail_mode=FailMode.FAIL_FALLBACK,
        is_required=True,
        rationale="MOIS API DEFAULT_TIMEOUT=15s, 안전 마진 적용",
    ),
    "location": NodePolicy(
        name="location",
        timeout_ms=3000,
        max_retries=2,
        cb_threshold=5,
        fail_mode=FailMode.FAIL_FALLBACK,
        is_required=True,
        rationale="gRPC PostGIS ~100ms, 3초면 충분",
    ),
    "general": NodePolicy(
        name="general",
        timeout_ms=30000,
        max_retries=2,
        cb_threshold=3,
        fail_mode=FailMode.FAIL_CLOSE,
        is_required=True,
        rationale="LLM HTTP_TIMEOUT.read=60s, 30초는 대부분 완료",
    ),
    # 선택 노드 (FAIL_OPEN/FALLBACK)
    "character": NodePolicy(
        name="character",
        timeout_ms=3000,
        max_retries=1,
        cb_threshold=3,
        fail_mode=FailMode.FAIL_OPEN,
        is_required=False,
        rationale="gRPC LocalCache ~1-3ms, 없어도 답변 가능",
    ),
    "collection_point": NodePolicy(
        name="collection_point",
        timeout_ms=10000,
        max_retries=2,
        cb_threshold=5,
        fail_mode=FailMode.FAIL_FALLBACK,
        is_required=False,
        rationale="KECO API DEFAULT_TIMEOUT=15s, 안전 마진 적용",
    ),
    "weather": NodePolicy(
        name="weather",
        timeout_ms=5000,
        max_retries=1,
        cb_threshold=3,
        fail_mode=FailMode.FAIL_OPEN,
        is_required=False,
        rationale="KMA API DEFAULT_TIMEOUT=10s, 보조 정보라 빠른 실패 허용",
    ),
    "web_search": NodePolicy(
        name="web_search",
        timeout_ms=10000,
        max_retries=2,
        cb_threshold=5,
        fail_mode=FailMode.FAIL_FALLBACK,
        is_required=False,
        rationale="DuckDuckGo timeout=10s, 검색 실패 시 일반 LLM 응답",
    ),
    "recyclable_price": NodePolicy(
        name="recyclable_price",
        timeout_ms=10000,
        max_retries=2,
        cb_threshold=5,
        fail_mode=FailMode.FAIL_FALLBACK,
        is_required=False,
        rationale="KECO API DEFAULT_TIMEOUT=15s, 시세 정보는 보조 컨텍스트",
    ),
    "image_generation": NodePolicy(
        name="image_generation",
        timeout_ms=30000,
        max_retries=1,
        cb_threshold=3,
        fail_mode=FailMode.FAIL_OPEN,
        is_required=False,
        rationale="DALL-E 10-30초 소요, 실패해도 텍스트 답변 가능",
    ),
}


def get_node_policy(node_name: str) -> NodePolicy:
    """노드 정책 조회.

    Args:
        node_name: 노드 이름

    Returns:
        NodePolicy (없으면 기본값 반환)
    """
    if node_name in NODE_POLICIES:
        return NODE_POLICIES[node_name]

    # 기본 정책: 보수적 설정
    return NodePolicy(
        name=node_name,
        timeout_ms=10000,
        max_retries=1,
        cb_threshold=5,
        fail_mode=FailMode.FAIL_OPEN,
        is_required=False,
        rationale="기본 정책 (정의되지 않은 노드)",
    )


# 필수/선택 컨텍스트 목록 (Aggregator에서 사용)
REQUIRED_CONTEXTS = frozenset(
    policy.name for policy in NODE_POLICIES.values() if policy.is_required
)
OPTIONAL_CONTEXTS = frozenset(
    policy.name for policy in NODE_POLICIES.values() if not policy.is_required
)


__all__ = [
    "NODE_POLICIES",
    "NodePolicy",
    "OPTIONAL_CONTEXTS",
    "REQUIRED_CONTEXTS",
    "get_node_policy",
]
