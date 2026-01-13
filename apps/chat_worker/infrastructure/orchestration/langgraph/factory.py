"""LangGraph Factory.

Intent-Routed Workflow with Subagent 패턴 그래프 생성.

아키텍처:
```
START → intent → router
                   │
        ┌──────────┼──────────┬───────────┐
        ▼          ▼          ▼           ▼
     waste    character   location    general
     (RAG)    (gRPC)      (gRPC)    (passthrough)
        │          │          │           │
        └──────────┴──────────┴───────────┘
                   │
                   ▼
                answer → END
```

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
)

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

    from chat_worker.application.integrations.character.ports import CharacterClientPort
    from chat_worker.application.integrations.location.ports import LocationClientPort
    from chat_worker.application.interaction.ports import InputRequesterPort
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.llm import LLMClientPort
    from chat_worker.application.ports.retrieval import RetrieverPort

logger = logging.getLogger(__name__)


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
    character_client: "CharacterClientPort | None" = None,
    location_client: "LocationClientPort | None" = None,
    input_requester: "InputRequesterPort | None" = None,
    checkpointer: "BaseCheckpointSaver | None" = None,
) -> StateGraph:
    """Chat 파이프라인 그래프 생성.

    Args:
        llm: LLM 클라이언트
        retriever: RAG 리트리버
        event_publisher: 이벤트 발행자 (SSE)
        character_client: Character gRPC 클라이언트 (선택)
        location_client: Location gRPC 클라이언트 (선택)
        input_requester: Human-in-the-Loop 입력 요청자 (선택)
        checkpointer: LangGraph 체크포인터 (세션 유지용)

    Returns:
        컴파일된 LangGraph

    Note:
        - character_client, location_client가 None이면 passthrough 노드 사용
        - input_requester가 있으면 Location Subagent에서 Human-in-the-Loop 활성화
        - checkpointer가 있으면 thread_id로 멀티턴 대화 컨텍스트 유지
    """
    # 핵심 노드 생성
    intent_node = create_intent_node(llm, event_publisher)
    rag_node = create_rag_node(retriever, event_publisher)
    answer_node = create_answer_node(llm, event_publisher)

    graph = StateGraph(dict)

    # 핵심 노드 등록
    graph.add_node("intent", intent_node)
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

    # Subagent 노드: Location (Human-in-the-Loop 지원)
    if location_client is not None:
        location_node = create_location_subagent_node(
            location_client=location_client,
            event_publisher=event_publisher,
            input_requester=input_requester,  # Human-in-the-Loop
        )
        if input_requester is not None:
            logger.info("Location subagent node created (gRPC + Human-in-the-Loop)")
        else:
            logger.info("Location subagent node created (gRPC only)")
    else:
        # Fallback: passthrough
        async def location_node(state: dict[str, Any]) -> dict[str, Any]:
            logger.warning("Location client not configured, using passthrough")
            return state

        logger.warning("Location subagent node using passthrough (no client)")

    # General 노드: passthrough
    async def general_node(state: dict[str, Any]) -> dict[str, Any]:
        return state

    # 노드 등록
    graph.add_node("character", character_node)
    graph.add_node("location", location_node)
    graph.add_node("general", general_node)

    # 엣지 연결
    graph.set_entry_point("intent")

    graph.add_conditional_edges(
        "intent",
        route_by_intent,
        {
            "waste": "waste_rag",
            "character": "character",
            "location": "location",
            "general": "general",
        },
    )

    for node_name in ["waste_rag", "character", "location", "general"]:
        graph.add_edge(node_name, "answer")

    graph.add_edge("answer", END)

    # 체크포인터 연결 (멀티턴 대화 컨텍스트 유지)
    if checkpointer is not None:
        logger.info("Chat graph created with checkpointer (multi-turn enabled)")
        return graph.compile(checkpointer=checkpointer)

    logger.info("Chat graph created without checkpointer (single-turn only)")
    return graph.compile()
