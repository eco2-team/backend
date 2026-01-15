"""LangGraph Factory.

Intent-Routed Workflow with Subagent + Feedback Loop 패턴 그래프 생성.

아키텍처:
```
START → intent → [vision?] → router
                               │
                    ┌──────────┼──────────┬───────────┬───────────┐
                    ▼          ▼          ▼           ▼           ▼
                 waste    character   location   web_search   general
                 (RAG)    (gRPC)      (gRPC)    (DuckDuckGo)  (passthrough)
                    │          │          │           │           │
                    ▼          │          │           │           │
               [feedback]      │          │           │           │
                  │ ↓ ↓        │          │           │           │
              fallback?        │          │           │           │
                  │ ↓          │          │           │           │
                  │ web_search │          │           │           │
                    └──────────┴──────────┴───────────┴───────────┘
                                          │
                                          ▼
                                   [summarize?] ← LangGraph 1.0+ Context Compression
                                          │
                                          ▼
                                       answer → END
```

Feedback Loop (논문 참조):
- "What Makes Large Language Models Reason in (Multi-Turn) Code Generation?"
- RAG 결과 품질 평가 후 Fallback 결정
- 저품질 → Web Search → General LLM 체인

Vision 노드:
- image_url이 있으면 Vision 분석 수행
- classification_result를 state에 저장
- RAG 노드가 분류 결과 활용

체크포인팅:
- Scan: Stateless Reducer + Redis (단일 요청)
- Chat: LangGraph + PostgreSQL (멀티턴 대화, 장기 세션)

컨텍스트 압축 (LangGraph 1.0+):
- enable_summarization=True로 활성화
- 토큰 임계값(max_tokens_before_summary) 초과 시 이전 대화 요약
- summary + recent_messages로 컨텍스트 구성
- langmem SummarizationNode 패턴 참조

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
    create_feedback_node,
    create_intent_node,
    create_location_subagent_node,
    create_rag_node,
    create_vision_node,
    route_after_feedback,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.web_search_node import (
    create_web_search_node,
)
from chat_worker.infrastructure.orchestration.langgraph.state import ChatState
from chat_worker.infrastructure.orchestration.langgraph.summarization import (
    SummarizationNode,
)

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

    from chat_worker.application.ports.cache import CachePort
    from chat_worker.application.ports.character_client import CharacterClientPort
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.input_requester import InputRequesterPort
    from chat_worker.application.ports.llm import LLMClientPort
    from chat_worker.application.ports.llm_evaluator import LLMFeedbackEvaluatorPort
    from chat_worker.application.ports.location_client import LocationClientPort
    from chat_worker.application.ports.prompt_loader import PromptLoaderPort
    from chat_worker.application.ports.retrieval import RetrieverPort
    from chat_worker.application.ports.vision import VisionModelPort
    from chat_worker.application.ports.web_search import WebSearchPort
    from chat_worker.application.services.fallback_orchestrator import (
        FallbackOrchestrator,
    )

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
    prompt_loader: "PromptLoaderPort",
    vision_model: "VisionModelPort | None" = None,
    character_client: "CharacterClientPort | None" = None,
    location_client: "LocationClientPort | None" = None,
    web_search_client: "WebSearchPort | None" = None,
    cache: "CachePort | None" = None,  # P2: Intent 캐싱용 (CachePort 추상화)
    input_requester: "InputRequesterPort | None" = None,  # Reserved for future use
    checkpointer: "BaseCheckpointSaver | None" = None,
    fallback_orchestrator: "FallbackOrchestrator | None" = None,  # Fallback 체인
    llm_evaluator: "LLMFeedbackEvaluatorPort | None" = None,  # LLM 기반 정밀 평가
    enable_summarization: bool = False,  # LangGraph 1.0+ 컨텍스트 압축
    max_tokens_before_summary: int = 3072,  # 요약 트리거 임계값
) -> StateGraph:
    """Chat 파이프라인 그래프 생성.

    Args:
        llm: LLM 클라이언트
        retriever: RAG 리트리버
        event_publisher: 이벤트 발행자 (SSE)
        prompt_loader: 프롬프트 로더 (필수)
        vision_model: Vision 모델 클라이언트 (선택, 이미지 분류)
        character_client: Character gRPC 클라이언트 (선택)
        location_client: Location gRPC 클라이언트 (선택)
        web_search_client: 웹 검색 클라이언트 (선택, DuckDuckGo/Tavily/Fallback)
        input_requester: Reserved for future use (현재 미사용)
        checkpointer: LangGraph 체크포인터 (세션 유지용)
        fallback_orchestrator: Fallback 체인 오케스트레이터 (선택)
        llm_evaluator: LLM 기반 품질 평가기 (선택, 정밀 평가용)
        enable_summarization: 컨텍스트 압축 활성화 (멀티턴 대화용)
        max_tokens_before_summary: 요약 트리거 임계값 (기본 3072)

    Returns:
        컴파일된 LangGraph

    Note:
        - vision_model이 있고 image_url이 있으면 Vision 분석 수행
        - character_client, location_client, web_search_client가 None이면 passthrough
        - 모든 Subagent는 gRPC로 통신 (web_search는 외부 API)
        - checkpointer가 있으면 thread_id로 멀티턴 대화 컨텍스트 유지
        - fallback_orchestrator가 있으면 저품질 시 Fallback 실행
        - llm_evaluator가 있으면 Rule 기반 평가 후 LLM 정밀 평가 수행
        - enable_summarization이 True면 컨텍스트 압축 수행
    """
    _ = input_requester  # Reserved for future use

    # 컨텍스트 압축 노드 (선택)
    if enable_summarization:
        summarization_node = SummarizationNode(
            llm=llm,
            max_tokens_before_summary=max_tokens_before_summary,
            prompt_loader=prompt_loader,
        )
        logger.info(
            "Summarization enabled (threshold=%d tokens)",
            max_tokens_before_summary,
        )
    else:
        summarization_node = None

    # 핵심 노드 생성
    intent_node = create_intent_node(
        llm, event_publisher, prompt_loader=prompt_loader, cache=cache
    )  # P2: Intent 캐싱
    rag_node = create_rag_node(retriever, event_publisher)
    answer_node = create_answer_node(llm, event_publisher, cache=cache)  # P3: Answer 캐싱

    # Vision 노드 (선택)
    if vision_model is not None:
        vision_node = create_vision_node(vision_model, event_publisher)
        logger.info("Vision node created")
    else:

        async def vision_node(state: dict[str, Any]) -> dict[str, Any]:
            logger.debug("Vision model not configured, skipping")
            return state

        logger.warning("Vision node using passthrough (no model)")

    # Feedback 노드 (선택) - RAG 품질 평가 및 Fallback
    # UseCase 조립 패턴: Node에서 Service + Port 조립
    if fallback_orchestrator is not None:
        feedback_node = create_feedback_node(
            fallback_orchestrator=fallback_orchestrator,
            event_publisher=event_publisher,
            llm_evaluator=llm_evaluator,  # 선택적 LLM 평가
            web_search_client=web_search_client,  # Fallback용 웹 검색
        )
        logger.info("Feedback node created (with Fallback chain)")
        feedback_enabled = True
    else:

        async def feedback_node(state: dict[str, Any]) -> dict[str, Any]:
            logger.debug("Fallback orchestrator not configured, skipping feedback")
            return state

        feedback_enabled = False
        logger.warning("Feedback node using passthrough (no fallback orchestrator)")

    # Router 노드 (조건부 라우팅을 위한 passthrough)
    async def router_node(state: dict[str, Any]) -> dict[str, Any]:
        return state

    graph = StateGraph(dict)

    # 핵심 노드 등록
    graph.add_node("intent", intent_node)
    graph.add_node("vision", vision_node)
    graph.add_node("router", router_node)
    graph.add_node("waste_rag", rag_node)
    graph.add_node("feedback", feedback_node)  # RAG 품질 평가 노드
    graph.add_node("answer", answer_node)

    # Subagent 노드: Character
    if character_client is not None:
        character_node = create_character_subagent_node(
            llm=llm,
            character_client=character_client,
            event_publisher=event_publisher,
            prompt_loader=prompt_loader,
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

    # Summarization 노드 등록 (선택)
    if summarization_node is not None:
        graph.add_node("summarize", summarization_node)
        logger.info("Summarization node registered")

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

    # 최종 목적지 결정: summarization 활성화 시 summarize → answer
    final_target = "summarize" if summarization_node is not None else "answer"

    # waste_rag → feedback → [summarize?] → answer (Feedback Loop)
    # 다른 노드들은 직접 [summarize?] → answer로
    if feedback_enabled:
        graph.add_edge("waste_rag", "feedback")
        graph.add_conditional_edges(
            "feedback",
            route_after_feedback,
            {
                "answer": final_target,
            },
        )
    else:
        graph.add_edge("waste_rag", final_target)

    for node_name in ["character", "location", "web_search", "general"]:
        graph.add_edge(node_name, final_target)

    # Summarization → Answer (활성화된 경우에만)
    if summarization_node is not None:
        graph.add_edge("summarize", "answer")

    graph.add_edge("answer", END)

    # 체크포인터 연결 (멀티턴 대화 컨텍스트 유지)
    if checkpointer is not None:
        logger.info("Chat graph created with checkpointer (multi-turn enabled)")
        return graph.compile(checkpointer=checkpointer)

    logger.info("Chat graph created without checkpointer (single-turn only)")
    return graph.compile()
