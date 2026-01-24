"""Dynamic Router Unit Tests.

Send API 기반 동적 라우팅 로직 검증.

Note:
    langgraph/langchain 의존성이 없으면 테스트를 건너뜁니다.
"""

from __future__ import annotations

import pytest

# langgraph가 없으면 테스트 건너뛰기
pytest.importorskip("langgraph", reason="langgraph not installed")

from chat_worker.infrastructure.orchestration.langgraph.routing.dynamic_router import (  # noqa: E402
    ConditionalEnrichment,
    EnrichmentRule,
    INTENT_TO_NODE,
    create_dynamic_router,
)


class TestDynamicRouter:
    """동적 라우터 테스트."""

    def test_primary_intent_routing(self):
        """주 intent → 해당 노드로 라우팅."""
        router = create_dynamic_router(
            enable_multi_intent=False,
            enable_enrichment=False,
            enable_conditional=False,
        )

        state = {"intent": "waste", "job_id": "test-123"}
        sends = router(state)

        assert len(sends) == 1
        assert sends[0].node == "waste_rag"

    def test_primary_intent_character(self):
        """character intent → character 노드."""
        router = create_dynamic_router(
            enable_multi_intent=False,
            enable_enrichment=False,
            enable_conditional=False,
        )

        state = {"intent": "character", "job_id": "test-123"}
        sends = router(state)

        assert len(sends) == 1
        assert sends[0].node == "character"

    def test_default_intent_fallback(self):
        """알 수 없는 intent → general 노드."""
        router = create_dynamic_router(
            enable_multi_intent=False,
            enable_enrichment=False,
            enable_conditional=False,
        )

        state = {"intent": "unknown_intent", "job_id": "test-123"}
        sends = router(state)

        assert len(sends) == 1
        assert sends[0].node == "general"

    def test_multi_intent_fanout(self):
        """Multi-intent → 여러 노드 병렬 Send."""
        router = create_dynamic_router(
            enable_multi_intent=True,
            enable_enrichment=False,
            enable_conditional=False,
        )

        state = {
            "intent": "waste",
            "additional_intents": ["collection_point", "character"],
            "job_id": "test-123",
        }
        sends = router(state)

        # waste + collection_point + character = 3개
        assert len(sends) == 3
        nodes = {s.node for s in sends}
        assert nodes == {"waste_rag", "collection_point", "character"}

    def test_multi_intent_deduplication(self):
        """중복 intent → 중복 제거."""
        router = create_dynamic_router(
            enable_multi_intent=True,
            enable_enrichment=False,
            enable_conditional=False,
        )

        state = {
            "intent": "waste",
            "additional_intents": ["waste"],  # 주 intent와 동일
            "job_id": "test-123",
        }
        sends = router(state)

        # 중복 제거되어 1개만
        assert len(sends) == 1
        assert sends[0].node == "waste_rag"

    def test_enrichment_waste_adds_weather(self):
        """waste intent → weather enrichment 자동 추가."""
        router = create_dynamic_router(
            enable_multi_intent=False,
            enable_enrichment=True,
            enable_conditional=False,
        )

        state = {"intent": "waste", "job_id": "test-123"}
        sends = router(state)

        # waste_rag + weather (enrichment)
        assert len(sends) == 2
        nodes = {s.node for s in sends}
        assert nodes == {"waste_rag", "weather"}

    def test_enrichment_bulk_waste_adds_weather(self):
        """bulk_waste intent → weather enrichment 자동 추가."""
        router = create_dynamic_router(
            enable_multi_intent=False,
            enable_enrichment=True,
            enable_conditional=False,
        )

        state = {"intent": "bulk_waste", "job_id": "test-123"}
        sends = router(state)

        # bulk_waste + weather (enrichment)
        assert len(sends) == 2
        nodes = {s.node for s in sends}
        assert nodes == {"bulk_waste", "weather"}

    def test_enrichment_no_duplicate(self):
        """이미 활성화된 노드는 enrichment로 중복 추가 안 됨."""
        router = create_dynamic_router(
            enable_multi_intent=True,
            enable_enrichment=True,
            enable_conditional=False,
        )

        state = {
            "intent": "waste",
            "additional_intents": ["weather"],  # 이미 weather 포함
            "job_id": "test-123",
        }
        sends = router(state)

        # waste_rag + weather (중복 없이 1번만)
        assert len(sends) == 2
        nodes = {s.node for s in sends}
        assert nodes == {"waste_rag", "weather"}

    def test_conditional_enrichment_with_location(self):
        """user_location이 있으면 weather 조건부 추가."""
        router = create_dynamic_router(
            enable_multi_intent=False,
            enable_enrichment=False,
            enable_conditional=True,
        )

        # waste는 조건부 enrichment 제외 대상이 아님
        state = {
            "intent": "waste",  # weather enrichment 허용 intent
            "user_location": {"lat": 37.5665, "lon": 126.9780},
            "job_id": "test-123",
        }
        sends = router(state)

        # waste_rag + weather (조건부 enrichment)
        assert len(sends) == 2
        nodes = {s.node for s in sends}
        assert nodes == {"waste_rag", "weather"}

    def test_conditional_enrichment_excluded_intent(self):
        """제외 intent면 조건부 enrichment 안 됨."""
        router = create_dynamic_router(
            enable_multi_intent=False,
            enable_enrichment=False,
            enable_conditional=True,
        )

        state = {
            "intent": "weather",  # 제외 intent
            "user_location": {"lat": 37.5665, "lon": 126.9780},
            "job_id": "test-123",
        }
        sends = router(state)

        # weather만 (조건부 enrichment 제외됨)
        assert len(sends) == 1
        assert sends[0].node == "weather"

    def test_conditional_enrichment_no_location(self):
        """user_location 없으면 조건부 enrichment 안 됨."""
        router = create_dynamic_router(
            enable_multi_intent=False,
            enable_enrichment=False,
            enable_conditional=True,
        )

        state = {
            "intent": "character",
            # user_location 없음
            "job_id": "test-123",
        }
        sends = router(state)

        # character만
        assert len(sends) == 1
        assert sends[0].node == "character"

    def test_full_dynamic_routing(self):
        """모든 기능 활성화 시 종합 테스트."""
        router = create_dynamic_router(
            enable_multi_intent=True,
            enable_enrichment=True,
            enable_conditional=True,
        )

        state = {
            "intent": "waste",
            "additional_intents": ["collection_point"],
            "user_location": {"lat": 37.5665, "lon": 126.9780},
            "job_id": "test-123",
        }
        sends = router(state)

        # waste_rag (주 intent)
        # + collection_point (multi-intent)
        # + weather (enrichment for waste)
        # = 3개 (조건부 weather는 enrichment와 중복이라 추가 안 됨)
        nodes = {s.node for s in sends}
        assert "waste_rag" in nodes
        assert "collection_point" in nodes
        assert "weather" in nodes

    def test_empty_additional_intents(self):
        """additional_intents가 빈 리스트일 때."""
        router = create_dynamic_router(
            enable_multi_intent=True,
            enable_enrichment=False,
            enable_conditional=False,
        )

        state = {
            "intent": "waste",
            "additional_intents": [],
            "job_id": "test-123",
        }
        sends = router(state)

        assert len(sends) == 1
        assert sends[0].node == "waste_rag"

    def test_conditional_web_search_for_low_confidence_general(self):
        """general intent + 낮은 confidence → web_search enrichment 추가."""
        router = create_dynamic_router(
            enable_multi_intent=False,
            enable_enrichment=False,
            enable_conditional=True,
        )

        state = {
            "intent": "general",
            "intent_confidence": 0.55,  # 낮은 확신도
            "message": "대홍수 평점 알려줘",
            "job_id": "test-123",
        }
        sends = router(state)

        nodes = {s.node for s in sends}
        assert "general" in nodes
        assert "web_search" in nodes

    def test_conditional_web_search_not_triggered_for_high_confidence_general(self):
        """general intent + 높은 confidence → web_search 미추가."""
        router = create_dynamic_router(
            enable_multi_intent=False,
            enable_enrichment=False,
            enable_conditional=True,
        )

        state = {
            "intent": "general",
            "intent_confidence": 0.90,  # 높은 확신도
            "message": "안녕하세요",
            "job_id": "test-123",
        }
        sends = router(state)

        nodes = {s.node for s in sends}
        assert nodes == {"general"}

    def test_conditional_web_search_for_non_general_with_keyword(self):
        """비-general intent + 실시간 키워드 → web_search enrichment 추가."""
        router = create_dynamic_router(
            enable_multi_intent=False,
            enable_enrichment=False,
            enable_conditional=True,
        )

        state = {
            "intent": "waste",
            "intent_confidence": 0.90,
            "message": "최신 분리배출 정책 알려줘",  # "최신" 키워드
            "job_id": "test-123",
        }
        sends = router(state)

        nodes = {s.node for s in sends}
        assert "waste_rag" in nodes
        assert "web_search" in nodes


class TestEnrichmentRules:
    """Enrichment 규칙 테스트."""

    def test_enrichment_rule_structure(self):
        """EnrichmentRule 구조 검증."""
        rule = EnrichmentRule(
            intent="waste",
            enrichments=("weather", "location"),
            description="테스트 규칙",
        )

        assert rule.intent == "waste"
        assert rule.enrichments == ("weather", "location")
        assert rule.description == "테스트 규칙"

    def test_conditional_enrichment_structure(self):
        """ConditionalEnrichment 구조 검증."""
        rule = ConditionalEnrichment(
            node="weather",
            condition=lambda state: state.get("user_location") is not None,
            exclude_intents=("weather", "general"),
            description="위치 있으면 날씨 추가",
        )

        assert rule.node == "weather"
        assert rule.exclude_intents == ("weather", "general")
        assert rule.condition({"user_location": {"lat": 37.5}})
        assert not rule.condition({})


class TestIntentToNodeMapping:
    """Intent → Node 매핑 테스트."""

    def test_all_intents_mapped(self):
        """모든 표준 intent가 매핑되어 있는지."""
        expected_intents = [
            "waste",
            "character",
            "location",
            # web_search는 GENERAL로 통합됨 (PR #441)
            "bulk_waste",
            "recyclable_price",
            "collection_point",
            "weather",
            "image_generation",
            "general",
        ]

        for intent in expected_intents:
            assert intent in INTENT_TO_NODE, f"Missing mapping for intent: {intent}"

    def test_waste_maps_to_waste_rag(self):
        """waste → waste_rag (RAG 노드)."""
        assert INTENT_TO_NODE["waste"] == "waste_rag"
