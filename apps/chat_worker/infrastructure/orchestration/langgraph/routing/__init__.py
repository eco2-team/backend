"""LangGraph Dynamic Routing.

Send API 기반 동적 라우팅 모듈.

기능:
- Multi-intent fanout: 여러 intent → 여러 노드 병렬 실행
- Intent 기반 enrichment: 특정 intent에 보조 노드 자동 추가
- 조건부 enrichment: state 조건 만족 시 노드 추가
"""

from chat_worker.infrastructure.orchestration.langgraph.routing.dynamic_router import (
    create_dynamic_router,
    EnrichmentRule,
    ConditionalEnrichment,
    ENRICHMENT_RULES,
    CONDITIONAL_ENRICHMENTS,
    INTENT_TO_NODE,
)

__all__ = [
    "create_dynamic_router",
    "EnrichmentRule",
    "ConditionalEnrichment",
    "ENRICHMENT_RULES",
    "CONDITIONAL_ENRICHMENTS",
    "INTENT_TO_NODE",
]
