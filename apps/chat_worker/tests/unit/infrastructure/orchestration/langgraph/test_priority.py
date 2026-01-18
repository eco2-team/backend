"""Priority Scheduling 단위 테스트.

테스트 대상:
- Priority enum
- NODE_PRIORITY 매핑
- NODE_DEADLINE_MS 매핑
- calculate_effective_priority (Aging 알고리즘)
- get_node_priority, get_node_deadline 헬퍼
"""

from __future__ import annotations

import time


from chat_worker.infrastructure.orchestration.langgraph.priority import (
    AGING_MAX_BOOST,
    DEFAULT_DEADLINE_MS,
    FALLBACK_PRIORITY_PENALTY,
    NODE_DEADLINE_MS,
    NODE_PRIORITY,
    Priority,
    calculate_effective_priority,
    get_node_deadline,
    get_node_priority,
)


class TestPriorityEnum:
    """Priority enum 테스트."""

    def test_priority_ordering(self):
        """우선순위 순서: 낮은 값 = 높은 우선순위."""
        assert Priority.CRITICAL < Priority.HIGH
        assert Priority.HIGH < Priority.NORMAL
        assert Priority.NORMAL < Priority.LOW
        assert Priority.LOW < Priority.BACKGROUND

    def test_priority_values(self):
        """우선순위 값 확인."""
        assert Priority.CRITICAL == 0
        assert Priority.HIGH == 25
        assert Priority.NORMAL == 50
        assert Priority.LOW == 75
        assert Priority.BACKGROUND == 100


class TestNodePriority:
    """NODE_PRIORITY 매핑 테스트."""

    def test_critical_nodes(self):
        """필수 컨텍스트 노드는 CRITICAL."""
        critical_nodes = ["waste_rag", "bulk_waste", "location", "collection_point"]
        for node in critical_nodes:
            assert NODE_PRIORITY[node] == Priority.CRITICAL

    def test_high_nodes(self):
        """주요 서비스 노드는 HIGH."""
        high_nodes = ["character", "general", "web_search"]
        for node in high_nodes:
            assert NODE_PRIORITY[node] == Priority.HIGH

    def test_normal_nodes(self):
        """일반 노드는 NORMAL."""
        normal_nodes = ["recyclable_price", "image_generation"]
        for node in normal_nodes:
            assert NODE_PRIORITY[node] == Priority.NORMAL

    def test_low_nodes(self):
        """보조 노드는 LOW."""
        assert NODE_PRIORITY["weather"] == Priority.LOW

    def test_get_node_priority_known(self):
        """알려진 노드 우선순위 조회."""
        assert get_node_priority("weather") == Priority.LOW
        assert get_node_priority("waste_rag") == Priority.CRITICAL

    def test_get_node_priority_unknown(self):
        """알 수 없는 노드는 NORMAL."""
        assert get_node_priority("unknown_node") == Priority.NORMAL


class TestNodeDeadline:
    """NODE_DEADLINE_MS 매핑 테스트."""

    def test_image_generation_deadline(self):
        """이미지 생성은 30초 (LLM 작업)."""
        assert NODE_DEADLINE_MS["image_generation"] == 30000

    def test_grpc_service_deadline(self):
        """gRPC 서비스는 5초 (내부 서비스)."""
        assert NODE_DEADLINE_MS["character"] == 5000
        assert NODE_DEADLINE_MS["location"] == 5000

    def test_external_api_deadline(self):
        """외부 API는 8-10초."""
        assert NODE_DEADLINE_MS["weather"] == 8000
        assert NODE_DEADLINE_MS["web_search"] == 10000
        assert NODE_DEADLINE_MS["bulk_waste"] == 8000
        assert NODE_DEADLINE_MS["collection_point"] == 8000

    def test_rag_deadline(self):
        """RAG/벡터 검색은 8초."""
        assert NODE_DEADLINE_MS["waste_rag"] == 8000

    def test_local_data_deadline(self):
        """로컬 데이터는 5초."""
        assert NODE_DEADLINE_MS["recyclable_price"] == 5000

    def test_get_node_deadline_known(self):
        """알려진 노드 deadline 조회."""
        assert get_node_deadline("image_generation") == 30000
        assert get_node_deadline("weather") == 8000

    def test_get_node_deadline_unknown(self):
        """알 수 없는 노드는 기본값."""
        assert get_node_deadline("unknown_node") == DEFAULT_DEADLINE_MS


class TestAgingAlgorithm:
    """Aging 알고리즘 테스트 (calculate_effective_priority)."""

    def test_no_aging_within_threshold(self):
        """Threshold 이내: Aging 없음."""
        now = time.time()
        deadline_ms = 10000  # 10초

        # 즉시 (0% 경과)
        priority = calculate_effective_priority(
            base_priority=Priority.NORMAL,
            created_at=now,
            deadline_ms=deadline_ms,
        )
        assert priority == Priority.NORMAL

        # 50% 경과 (threshold 80% 미만)
        priority = calculate_effective_priority(
            base_priority=Priority.NORMAL,
            created_at=now - 5.0,  # 5초 전
            deadline_ms=deadline_ms,
        )
        assert priority == Priority.NORMAL

    def test_aging_boost_at_threshold(self):
        """Threshold 초과: Aging 부스트 시작."""
        now = time.time()
        deadline_ms = 10000  # 10초

        # 80% 경과 (threshold 도달) → 부스트 시작
        priority = calculate_effective_priority(
            base_priority=Priority.LOW,  # 75
            created_at=now - 8.0,  # 8초 전 (80%)
            deadline_ms=deadline_ms,
        )
        # 80% 정확히 도달 → 부스트 0
        assert priority == Priority.LOW

        # 90% 경과 → 부스트 중간
        priority = calculate_effective_priority(
            base_priority=Priority.LOW,  # 75
            created_at=now - 9.0,  # 9초 전 (90%)
            deadline_ms=deadline_ms,
        )
        # 90% = threshold(80%) + 10% → boost_ratio = 0.5 → boost = 10
        # 75 - 10 = 65
        assert priority == 65

    def test_aging_max_boost_at_deadline(self):
        """Deadline 도달: 최대 부스트."""
        now = time.time()
        deadline_ms = 10000  # 10초

        # 100% 경과 (deadline 도달) → 최대 부스트
        priority = calculate_effective_priority(
            base_priority=Priority.LOW,  # 75
            created_at=now - 10.0,  # 10초 전 (100%)
            deadline_ms=deadline_ms,
        )
        # 75 - 20 (MAX_BOOST) = 55
        assert priority == Priority.LOW - AGING_MAX_BOOST

    def test_aging_beyond_deadline(self):
        """Deadline 초과: 최대 부스트 유지."""
        now = time.time()
        deadline_ms = 10000  # 10초

        # 150% 경과 (deadline 초과) → 최대 부스트 (더 이상 증가 안 함)
        priority = calculate_effective_priority(
            base_priority=Priority.LOW,  # 75
            created_at=now - 15.0,  # 15초 전 (150%)
            deadline_ms=deadline_ms,
        )
        # boost_ratio > 1 → clamped to MAX_BOOST
        assert priority == Priority.LOW - AGING_MAX_BOOST

    def test_fallback_penalty(self):
        """Fallback 결과: 페널티 적용."""
        now = time.time()

        # Fallback 아님
        priority_normal = calculate_effective_priority(
            base_priority=Priority.CRITICAL,  # 0
            created_at=now,
            deadline_ms=5000,
            is_fallback=False,
        )
        assert priority_normal == Priority.CRITICAL

        # Fallback → 페널티 적용
        priority_fallback = calculate_effective_priority(
            base_priority=Priority.CRITICAL,  # 0
            created_at=now,
            deadline_ms=5000,
            is_fallback=True,
        )
        assert priority_fallback == Priority.CRITICAL + FALLBACK_PRIORITY_PENALTY

    def test_combined_aging_and_fallback(self):
        """Aging + Fallback 동시 적용."""
        now = time.time()
        deadline_ms = 10000

        # 100% 경과 + Fallback
        priority = calculate_effective_priority(
            base_priority=Priority.NORMAL,  # 50
            created_at=now - 10.0,  # deadline 도달
            deadline_ms=deadline_ms,
            is_fallback=True,
        )
        # 50 - 20 (aging) + 15 (fallback) = 45
        expected = Priority.NORMAL - AGING_MAX_BOOST + FALLBACK_PRIORITY_PENALTY
        assert priority == expected

    def test_priority_clamped_to_valid_range(self):
        """우선순위는 0~100 범위로 제한."""
        now = time.time()

        # 하한: CRITICAL(0)에서 aging 적용해도 음수 안 됨
        priority = calculate_effective_priority(
            base_priority=Priority.CRITICAL,  # 0
            created_at=now - 10.0,
            deadline_ms=10000,
            is_fallback=False,
        )
        assert priority >= 0

        # 상한: BACKGROUND(100)에서 fallback 적용해도 100 초과 안 함
        priority = calculate_effective_priority(
            base_priority=Priority.BACKGROUND,  # 100
            created_at=now,
            deadline_ms=10000,
            is_fallback=True,
        )
        assert priority <= 100

    def test_zero_deadline_no_division_error(self):
        """deadline_ms=0: 나눗셈 오류 방지."""
        now = time.time()

        # deadline_ms=0 → deadline_ratio=0 → Aging 없음
        priority = calculate_effective_priority(
            base_priority=Priority.NORMAL,
            created_at=now - 10.0,
            deadline_ms=0,
        )
        assert priority == Priority.NORMAL


class TestMappingConsistency:
    """NODE_PRIORITY와 NODE_DEADLINE_MS 일관성 테스트."""

    def test_all_priority_nodes_have_deadline(self):
        """모든 NODE_PRIORITY 노드가 NODE_DEADLINE_MS에 있어야 함."""
        for node in NODE_PRIORITY:
            assert node in NODE_DEADLINE_MS, f"Node '{node}' missing deadline"

    def test_all_deadline_nodes_have_priority(self):
        """모든 NODE_DEADLINE_MS 노드가 NODE_PRIORITY에 있어야 함."""
        for node in NODE_DEADLINE_MS:
            assert node in NODE_PRIORITY, f"Node '{node}' missing priority"
