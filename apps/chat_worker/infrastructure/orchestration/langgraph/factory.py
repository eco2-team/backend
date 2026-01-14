"""LangGraph Factory.

Intent-Routed Workflow with Subagent 패턴 그래프 생성.

아키텍처:
```
START → intent → [vision?] → router
                               │
                    ┌──────────┼──────────┬───────────┬───────────┐
                    ▼          ▼          ▼           ▼           ▼
                 waste    character   location   web_search   general
                 (RAG)    (gRPC)      (gRPC)    (DuckDuckGo)  (passthrough)
                    │          │          │           │           │
                    └──────────┴──────────┴───────────┴───────────┘
                                          │
                                          ▼
                                       answer → END
```

Vision 노드:
- image_url이 있으면 Vision 분석 수행
- classification_result를 state에 저장
- RAG 노드가 분류 결과 활용

체크포인팅:
- Scan: Stateless Reducer + Redis (단일 요청)
- Chat: LangGraph + PostgreSQL (멀티턴 대화, 장기 세션)

왜 gRPC (동기) vs Celery (비동기)?
- LangGraph는 asyncio 기반 오케스트레이션
- gRPC는 grpc.aio로 asyncio 네이티브 지원 (~1-100ms)
- Celery는 Fire & Forget에 적합, 결과 대기(await)에 부적합
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langgraph.graph import END, StateGraph

from chat_worker.infrastructure.orchestration.langgraph.nodes import (
    create_answer_node,
    create_character_subagent_node,
    create_intent_node,
    create_location_subagent_node,
    create_rag_node,
    create_vision_node,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.web_search_node import (
    create_web_search_node,
)

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from redis.asyncio import Redis

    from chat_worker.application.integrations.character.ports import CharacterClientPort
    from chat_worker.application.integrations.location.ports import LocationClientPort
    from chat_worker.application.interaction.ports import InputRequesterPort
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.llm import LLMClientPort
    from chat_worker.application.ports.retrieval import RetrieverPort
    from chat_worker.application.ports.vision import VisionModelPort
    from chat_worker.application.ports.web_search import WebSearchPort

logger = logging.getLogger(__name__)


def route_after_intent(state: dict[str, Any]) -> str:
    """Intent 후 라우팅 - Vision 필요 여부 결정.

    Args:
        state: 현재 상태

    Returns:
        다음 노드 이름 (vision 또는 router)
    """
    # image_url이 있고 아직 분류 안됐으면 vision으로
    if state.get("image_url") and not state.get("classification_result"):
        return "vision"
    return "router"


def route_by_intent(state: dict[str, Any]) -> str:
    """의도 기반 라우팅.

    Args:
        state: 현재 상태 (intent 필드 포함)

    Returns:
        다음 노드 이름
    """
    return state.get("intent", "general")


def create_chat_graph(
    llm: "LLMClientPort",
    retriever: "RetrieverPort",
    event_publisher: "ProgressNotifierPort",
    vision_model: "VisionModelPort | None" = None,
    character_client: "CharacterClientPort | None" = None,
    location_client: "LocationClientPort | None" = None,
    web_search_client: "WebSearchPort | None" = None,
    redis: "Redis | None" = None,  # P2: Intent 캐싱용
    input_requester: "InputRequesterPort | None" = None,  # Reserved for future use
    checkpointer: "BaseCheckpointSaver | None" = None,
) -> StateGraph:
    """Chat 파이프라인 그래프 생성.

    Args:
        llm: LLM 클라이언트
        retriever: RAG 리트리버
        event_publisher: 이벤트 발행자 (SSE)
        vision_model: Vision 모델 클라이언트 (선택, 이미지 분류)
        character_client: Character gRPC 클라이언트 (선택)
        location_client: Location gRPC 클라이언트 (선택)
        web_search_client: 웹 검색 클라이언트 (선택, DuckDuckGo/Tavily)
        input_requester: Reserved for future use (현재 미사용)
        checkpointer: LangGraph 체크포인터 (세션 유지용)

    Returns:
        컴파일된 LangGraph

    Note:
        - vision_model이 있고 image_url이 있으면 Vision 분석 수행
        - character_client, location_client, web_search_client가 None이면 passthrough
        - 모든 Subagent는 gRPC로 통신 (web_search는 외부 API)
        - checkpointer가 있으면 thread_id로 멀티턴 대화 컨텍스트 유지
    """
    _ = input_requester  # Reserved for future use

    # 핵심 노드 생성
    intent_node = create_intent_node(llm, event_publisher, redis=redis)  # P2: 캐싱
    rag_node = create_rag_node(retriever, event_publisher)
    answer_node = create_answer_node(llm, event_publisher)

    # Vision 노드 (선택)
    if vision_model is not None:
        vision_node = create_vision_node(vision_model, event_publisher)
        logger.info("Vision node created")
    else:
        async def vision_node(state: dict[str, Any]) -> dict[str, Any]:
            logger.debug("Vision model not configured, skipping")
            return state
        logger.warning("Vision node using passthrough (no model)")

    # Router 노드 (조건부 라우팅을 위한 passthrough)
    async def router_node(state: dict[str, Any]) -> dict[str, Any]:
        return state

    graph = StateGraph(dict)

    # 핵심 노드 등록
    graph.add_node("intent", intent_node)
    graph.add_node("vision", vision_node)
    graph.add_node("router", router_node)
    graph.add_node("waste_rag", rag_node)
    graph.add_node("answer", answer_node)

    # Subagent 노드: Character
    if character_client is not None:
        character_node = create_character_subagent_node(
            llm=llm,
            character_client=character_client,
            event_publisher=event_publisher,
        )
        logger.info("Character subagent node created (gRPC)")
    else:
        # Fallback: passthrough
        async def character_node(state: dict[str, Any]) -> dict[str, Any]:
            logger.warning("Character client not configured, using passthrough")
            return state

        logger.warning("Character subagent node using passthrough (no client)")

    # Subagent 노드: Location (gRPC)
    if location_client is not None:
        location_node = create_location_subagent_node(
            location_client=location_client,
            event_publisher=event_publisher,
        )
        logger.info("Location subagent node created (gRPC)")
    else:
        # Fallback: passthrough
        async def location_node(state: dict[str, Any]) -> dict[str, Any]:
            logger.warning("Location client not configured, using passthrough")
            return state

        logger.warning("Location subagent node using passthrough (no client)")

    # Subagent 노드: Web Search
    if web_search_client is not None:
        web_search_node = create_web_search_node(
            web_search_client=web_search_client,
            event_publisher=event_publisher,
        )
        logger.info("Web search subagent node created (DuckDuckGo/Tavily)")
    else:
        # Fallback: passthrough
        async def web_search_node(state: dict[str, Any]) -> dict[str, Any]:
            logger.warning("Web search client not configured, using passthrough")
            return state

        logger.warning("Web search subagent node using passthrough (no client)")

    # General 노드: passthrough
    async def general_node(state: dict[str, Any]) -> dict[str, Any]:
        return state

    # 노드 등록
    graph.add_node("character", character_node)
    graph.add_node("location", location_node)
    graph.add_node("web_search", web_search_node)
    graph.add_node("general", general_node)

    # 엣지 연결
    graph.set_entry_point("intent")

    # Intent → Vision or Router
    graph.add_conditional_edges(
        "intent",
        route_after_intent,
        {
            "vision": "vision",
            "router": "router",
        },
    )

    # Vision → Router
    graph.add_edge("vision", "router")

    # Router → Intent-based routing
    graph.add_conditional_edges(
        "router",
        route_by_intent,
        {
            "waste": "waste_rag",
            "character": "character",
            "location": "location",
            "web_search": "web_search",
            "general": "general",
        },
    )

    for node_name in ["waste_rag", "character", "location", "web_search", "general"]:
        graph.add_edge(node_name, "answer")

    graph.add_edge("answer", END)

    # 체크포인터 연결 (멀티턴 대화 컨텍스트 유지)
    if checkpointer is not None:
        logger.info("Chat graph created with checkpointer (multi-turn enabled)")
        return graph.compile(checkpointer=checkpointer)

    logger.info("Chat graph created without checkpointer (single-turn only)")
    return graph.compile()
