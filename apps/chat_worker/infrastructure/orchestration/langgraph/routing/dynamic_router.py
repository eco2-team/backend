"""Dynamic Router - Send API 기반 동적 라우팅.

LangGraph의 Send API를 활용하여 런타임에 동적으로
여러 노드를 병렬 실행합니다.

기능:
1. Multi-intent fanout: additional_intents → 각각 병렬 Send
2. Intent 기반 enrichment: 특정 intent에 보조 노드 자동 추가
3. 조건부 enrichment: state 조건 만족 시 노드 추가

사용 예:
    사용자: "종이 어떻게 버려? 그리고 수거함도 알려줘"

    intent_node 결과:
        intent="waste", additional_intents=["collection_point"]

    dynamic_router 결과:
        Send("waste_rag", state)        # 주 intent
        Send("collection_point", state) # multi-intent fanout
        Send("weather", state)          # enrichment (waste → weather)

    → 3개 노드 병렬 실행!
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from langgraph.types import Send

logger = logging.getLogger(__name__)


# ============================================================
# Enrichment 규칙 정의
# ============================================================

@dataclass(frozen=True)
class EnrichmentRule:
    """Intent 기반 Enrichment 규칙.

    특정 intent가 감지되면 자동으로 추가할 보조 노드들을 정의.

    Attributes:
        intent: 트리거 intent
        enrichments: 자동 추가할 노드 목록
        description: 규칙 설명 (로깅용)
    """
    intent: str
    enrichments: tuple[str, ...]
    description: str = ""


@dataclass
class ConditionalEnrichment:
    """조건부 Enrichment 규칙.

    state 조건을 만족하면 노드를 추가.

    Attributes:
        node: 추가할 노드 이름
        condition: state를 받아 bool 반환하는 함수
        exclude_intents: 이 intent들이 주 intent면 추가 안 함
        description: 규칙 설명 (로깅용)
    """
    node: str
    condition: Callable[[dict[str, Any]], bool]
    exclude_intents: tuple[str, ...] = ()
    description: str = ""


# Intent → 자동 추가할 enrichment 노드들
ENRICHMENT_RULES: dict[str, EnrichmentRule] = {
    "waste": EnrichmentRule(
        intent="waste",
        enrichments=("weather",),
        description="분리배출 질문 시 날씨 팁 추가",
    ),
    "bulk_waste": EnrichmentRule(
        intent="bulk_waste",
        enrichments=("weather",),
        description="대형폐기물 질문 시 날씨 팁 추가",
    ),
    # collection_point, recyclable_price는 enrichment 불필요
}


# 조건부 Enrichment (state 기반)
CONDITIONAL_ENRICHMENTS: list[ConditionalEnrichment] = [
    ConditionalEnrichment(
        node="weather",
        condition=lambda state: (
            state.get("user_location") is not None
            and state.get("intent") not in ("weather", "general", "character")
        ),
        exclude_intents=("weather", "image_generation"),
        description="위치 정보가 있고 관련 intent면 날씨 추가",
    ),
]


# Intent → 실제 노드 이름 매핑
INTENT_TO_NODE: dict[str, str] = {
    "waste": "waste_rag",
    "character": "character",
    "location": "location",
    "web_search": "web_search",
    "bulk_waste": "bulk_waste",
    "recyclable_price": "recyclable_price",
    "collection_point": "collection_point",
    "weather": "weather",
    "image_generation": "image_generation",
    "general": "general",
}


# ============================================================
# Dynamic Router 구현
# ============================================================

def create_dynamic_router(
    enable_multi_intent: bool = True,
    enable_enrichment: bool = True,
    enable_conditional: bool = True,
    custom_enrichment_rules: dict[str, EnrichmentRule] | None = None,
    custom_conditional_enrichments: list[ConditionalEnrichment] | None = None,
):
    """동적 라우터 팩토리.

    Args:
        enable_multi_intent: Multi-intent fanout 활성화
        enable_enrichment: Intent 기반 enrichment 활성화
        enable_conditional: 조건부 enrichment 활성화
        custom_enrichment_rules: 커스텀 enrichment 규칙 (기본값 오버라이드)
        custom_conditional_enrichments: 커스텀 조건부 규칙 (기본값 오버라이드)

    Returns:
        dynamic_router 함수 (list[Send] 반환)
    """
    enrichment_rules = custom_enrichment_rules or ENRICHMENT_RULES
    conditional_enrichments = custom_conditional_enrichments or CONDITIONAL_ENRICHMENTS

    def dynamic_router(state: dict[str, Any]) -> list[Send]:
        """Send API로 동적 병렬 라우팅.

        실행 순서:
        1. 주 intent → 해당 노드
        2. additional_intents → 각각 노드 (multi-intent fanout)
        3. enrichment 규칙 → 보조 노드 자동 추가
        4. 조건부 enrichment → state 조건 만족 시 추가

        Args:
            state: LangGraph 상태

        Returns:
            list[Send] - 병렬 실행할 노드들
        """
        sends: list[Send] = []
        activated_nodes: set[str] = set()

        primary_intent = state.get("intent", "general")
        additional_intents = state.get("additional_intents", [])
        job_id = state.get("job_id", "")

        # 1. 주 intent 노드
        primary_node = INTENT_TO_NODE.get(primary_intent, "general")
        sends.append(Send(primary_node, state))
        activated_nodes.add(primary_node)

        logger.debug(
            "Dynamic router: primary intent",
            extra={
                "job_id": job_id,
                "intent": primary_intent,
                "node": primary_node,
            },
        )

        # 2. Multi-intent fanout (추가 intents)
        if enable_multi_intent and additional_intents:
            for intent in additional_intents:
                node = INTENT_TO_NODE.get(intent, intent)
                if node not in activated_nodes:
                    sends.append(Send(node, state))
                    activated_nodes.add(node)

                    logger.debug(
                        "Dynamic router: multi-intent fanout",
                        extra={
                            "job_id": job_id,
                            "intent": intent,
                            "node": node,
                        },
                    )

        # 3. Intent 기반 Enrichment (규칙 기반)
        if enable_enrichment and primary_intent in enrichment_rules:
            rule = enrichment_rules[primary_intent]
            for enrichment_node in rule.enrichments:
                if enrichment_node not in activated_nodes:
                    sends.append(Send(enrichment_node, state))
                    activated_nodes.add(enrichment_node)

                    logger.debug(
                        "Dynamic router: enrichment",
                        extra={
                            "job_id": job_id,
                            "node": enrichment_node,
                            "rule": rule.description,
                        },
                    )

        # 4. 조건부 Enrichment (state 기반)
        if enable_conditional:
            for rule in conditional_enrichments:
                node = rule.node

                # 이미 활성화됨
                if node in activated_nodes:
                    continue

                # 제외 intent
                if primary_intent in rule.exclude_intents:
                    continue

                # 조건 체크
                try:
                    if rule.condition(state):
                        sends.append(Send(node, state))
                        activated_nodes.add(node)

                        logger.debug(
                            "Dynamic router: conditional enrichment",
                            extra={
                                "job_id": job_id,
                                "node": node,
                                "rule": rule.description,
                            },
                        )
                except Exception as e:
                    logger.warning(
                        f"Conditional enrichment check failed: {e}",
                        extra={"job_id": job_id, "node": node},
                    )

        logger.info(
            "Dynamic router completed",
            extra={
                "job_id": job_id,
                "primary_intent": primary_intent,
                "total_nodes": len(sends),
                "nodes": list(activated_nodes),
            },
        )

        return sends

    return dynamic_router


__all__ = [
    "create_dynamic_router",
    "EnrichmentRule",
    "ConditionalEnrichment",
    "ENRICHMENT_RULES",
    "CONDITIONAL_ENRICHMENTS",
    "INTENT_TO_NODE",
]
