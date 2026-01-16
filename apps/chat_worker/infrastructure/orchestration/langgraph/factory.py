"""LangGraph Factory.

Intent-Routed Workflow with Dynamic Routing (Send API) 패턴 그래프 생성.

아키텍처 (v2 - Dynamic Routing):
```
START → intent → [vision?] → dynamic_router
                                    │
                    ╔═══════════════╪═══════════════╗
                    ║   Send API (병렬 실행)         ║
                    ║   ┌─────┬─────┼─────┬─────┐   ║
                    ║   ▼     ▼     ▼     ▼     ▼   ║
                    ║ waste char  loc  bulk  web   ║
                    ║ (RAG) (gRPC)(Kakao)(MOIS)(DDG)║
                    ║   │     │     │     │     │   ║
                    ║   ▼     ▼     ▼     ▼     ▼   ║
                    ║  [feedback]  │     │     │   ║
                    ╚═══════╪══════╧═════╧═════╧═══╝
                            │
                            ▼
                       aggregator ← 결과 수집
                            │
                            ▼
                     [summarize?] ← Context Compression
                            │
                            ▼
                         answer → END
```

Dynamic Routing (Send API):
1. Multi-intent fanout: additional_intents → 각각 병렬 Send
2. Intent 기반 enrichment: 특정 intent에 보조 노드 자동 추가
   - waste → weather (분리배출 + 날씨 팁)
   - bulk_waste → weather (대형폐기물 + 날씨)
3. 조건부 enrichment: state 조건 만족 시 노드 추가
   - user_location 있으면 weather 자동 추가

예시:
    사용자: "종이 어떻게 버려? 그리고 수거함도 알려줘"

    intent_node 결과:
        intent="waste", additional_intents=["collection_point"]

    dynamic_router 결과:
        Send("waste_rag", state)        # 주 intent
        Send("collection_point", state) # multi-intent fanout
        Send("weather", state)          # enrichment (waste → weather)

    → 3개 노드 병렬 실행!

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
    create_aggregator_node,
    create_answer_node,
    create_bulk_waste_node,
    create_character_subagent_node,
    create_collection_point_node,
    create_feedback_node,
    create_image_generation_node,
    create_intent_node,
    create_location_subagent_node,
    create_rag_node,
    create_recyclable_price_node,
    create_vision_node,
    create_weather_node,
    route_after_feedback,
)
from chat_worker.infrastructure.orchestration.langgraph.routing import (
    create_dynamic_router,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.kakao_place_node import (
    create_kakao_place_node,
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

    from chat_worker.application.ports.bulk_waste_client import BulkWasteClientPort
    from chat_worker.application.ports.cache import CachePort
    from chat_worker.application.ports.collection_point_client import (
        CollectionPointClientPort,
    )
    from chat_worker.application.ports.image_generator import ImageGeneratorPort
    from chat_worker.application.ports.recyclable_price_client import (
        RecyclablePriceClientPort,
    )
    from chat_worker.application.ports.weather_client import WeatherClientPort
    from chat_worker.application.ports.character_client import CharacterClientPort
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.input_requester import InputRequesterPort
    from chat_worker.application.ports.kakao_local_client import KakaoLocalClientPort
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
    """의도 기반 라우팅 (Legacy - 단일 노드 라우팅).

    Note:
        동적 라우팅(Send API)이 활성화되면 이 함수는 사용되지 않습니다.
        하위 호환성을 위해 유지합니다.

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
    kakao_client: "KakaoLocalClientPort | None" = None,  # 카카오 장소 검색 (HTTP)
    web_search_client: "WebSearchPort | None" = None,
    bulk_waste_client: "BulkWasteClientPort | None" = None,  # 대형폐기물 정보 (행정안전부 API)
    recyclable_price_client: "RecyclablePriceClientPort | None" = None,  # 재활용자원 시세 (한국환경공단)
    weather_client: "WeatherClientPort | None" = None,  # 날씨 정보 (기상청 API)
    collection_point_client: "CollectionPointClientPort | None" = None,  # 수거함 위치 (KECO API)
    image_generator: "ImageGeneratorPort | None" = None,  # 이미지 생성 (Responses API)
    image_default_size: str = "1024x1024",  # 이미지 기본 크기
    image_default_quality: str = "medium",  # 이미지 기본 품질
    cache: "CachePort | None" = None,  # P2: Intent 캐싱용 (CachePort 추상화)
    input_requester: "InputRequesterPort | None" = None,  # Reserved for future use
    checkpointer: "BaseCheckpointSaver | None" = None,
    fallback_orchestrator: "FallbackOrchestrator | None" = None,  # Fallback 체인
    llm_evaluator: "LLMFeedbackEvaluatorPort | None" = None,  # LLM 기반 정밀 평가
    enable_summarization: bool = False,  # LangGraph 1.0+ 컨텍스트 압축
    summarization_model: str | None = None,  # 동적 설정용 모델명 (예: "gpt-5.2")
    max_tokens_before_summary: int | None = None,  # None이면 context-output 동적 계산
    max_summary_tokens: int | None = None,  # None이면 15% 동적 계산
    keep_recent_messages: int | None = None,  # None이면 PRUNE_PROTECT 기반 계산
    enable_dynamic_routing: bool = True,  # Send API 동적 라우팅
    enable_multi_intent: bool = True,  # Multi-intent fanout
    enable_enrichment: bool = True,  # Intent 기반 enrichment
) -> StateGraph:
    """Chat 파이프라인 그래프 생성.

    Args:
        llm: LLM 클라이언트
        retriever: RAG 리트리버
        event_publisher: 이벤트 발행자 (SSE)
        prompt_loader: 프롬프트 로더 (필수)
        vision_model: Vision 모델 클라이언트 (선택, 이미지 분류)
        character_client: Character gRPC 클라이언트 (선택)
        location_client: Location gRPC 클라이언트 (선택, Eco² 내부 DB)
        kakao_client: 카카오 로컬 클라이언트 (선택, 일반 장소 검색)
        web_search_client: 웹 검색 클라이언트 (선택, DuckDuckGo/Tavily/Fallback)
        bulk_waste_client: 대형폐기물 클라이언트 (선택, 행정안전부 API)
        recyclable_price_client: 재활용자원 시세 클라이언트 (선택, 한국환경공단)
        image_generator: 이미지 생성 클라이언트 (선택, Responses API)
        input_requester: Reserved for future use (현재 미사용)
        checkpointer: LangGraph 체크포인터 (세션 유지용)
        fallback_orchestrator: Fallback 체인 오케스트레이터 (선택)
        llm_evaluator: LLM 기반 품질 평가기 (선택, 정밀 평가용)
        enable_summarization: 컨텍스트 압축 활성화 (멀티턴 대화용)
        summarization_model: 동적 설정용 모델명 (예: "gpt-5.2", context-output 트리거 자동 계산)
        max_tokens_before_summary: 요약 트리거 임계값 (None이면 context-output 동적 계산)
        max_summary_tokens: 구조화된 요약 최대 토큰 (None이면 15% 동적 계산, min 20K)
        keep_recent_messages: 유지할 최근 메시지 수 (None이면 PRUNE_PROTECT 기반 계산)
        enable_dynamic_routing: Send API 동적 라우팅 활성화 (기본 True)
        enable_multi_intent: Multi-intent fanout 활성화 (기본 True)
        enable_enrichment: Intent 기반 enrichment 활성화 (기본 True)

    Returns:
        컴파일된 LangGraph

    Note:
        - vision_model이 있고 image_url이 있으면 Vision 분석 수행
        - character_client, location_client, web_search_client, bulk_waste_client가 None이면 passthrough
        - 모든 Subagent는 gRPC로 통신 (web_search, bulk_waste는 외부 HTTP API)
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
            model_name=summarization_model,  # 동적 설정: context-output 트리거
            max_tokens_before_summary=max_tokens_before_summary,  # None이면 동적 계산
            max_summary_tokens=max_summary_tokens,  # None이면 동적 계산
            keep_recent_messages=keep_recent_messages,  # None이면 동적 계산
            prompt_loader=prompt_loader,
        )
        # 로깅은 SummarizationNode 내부에서 처리됨
        if summarization_model:
            logger.info(
                "Summarization enabled with dynamic config (model=%s)",
                summarization_model,
            )
        else:
            logger.info(
                "Summarization enabled with static config (threshold=%s, max_summary=%s, keep_recent=%s)",
                max_tokens_before_summary or "default",
                max_summary_tokens or "default",
                keep_recent_messages or "default",
            )
    else:
        summarization_node = None

    # 핵심 노드 생성
    intent_node = create_intent_node(
        llm, event_publisher, prompt_loader=prompt_loader, cache=cache
    )  # P2: Intent 캐싱
    rag_node = create_rag_node(retriever, event_publisher)
    answer_node = create_answer_node(llm, cache=cache)  # P3: Answer 캐싱 (네이티브 스트리밍)

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

    # Subagent 노드: Location (카카오맵 HTTP)
    # gRPC location_client는 미사용 (deprecated)
    _ = location_client  # suppress unused warning
    if kakao_client is not None:
        location_node = create_kakao_place_node(
            kakao_client=kakao_client,
            event_publisher=event_publisher,
        )
        logger.info("Location subagent node created (Kakao HTTP)")
    else:
        # Fallback: passthrough
        async def location_node(state: dict[str, Any]) -> dict[str, Any]:
            logger.warning("Kakao client not configured, using passthrough")
            return state

        logger.warning("Location subagent node using passthrough (no Kakao client)")

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

    # Subagent 노드: Bulk Waste (대형폐기물 - 행정안전부 API)
    if bulk_waste_client is not None:
        bulk_waste_node = create_bulk_waste_node(
            bulk_waste_client=bulk_waste_client,
            event_publisher=event_publisher,
        )
        logger.info("Bulk waste subagent node created (MOIS API)")
    else:
        # Fallback: passthrough
        async def bulk_waste_node(state: dict[str, Any]) -> dict[str, Any]:
            logger.warning("Bulk waste client not configured, using passthrough")
            return state

        logger.warning("Bulk waste subagent node using passthrough (no client)")

    # Subagent 노드: Recyclable Price (재활용자원 시세 - 한국환경공단)
    if recyclable_price_client is not None:
        recyclable_price_node = create_recyclable_price_node(
            price_client=recyclable_price_client,
            event_publisher=event_publisher,
        )
        logger.info("Recyclable price subagent node created (KECO)")
    else:
        # Fallback: passthrough
        async def recyclable_price_node(state: dict[str, Any]) -> dict[str, Any]:
            logger.warning("Recyclable price client not configured, using passthrough")
            return state

        logger.warning("Recyclable price subagent node using passthrough (no client)")

    # Subagent 노드: Weather (기상청 API) - 병렬 실행 가능
    if weather_client is not None:
        weather_node = create_weather_node(
            weather_client=weather_client,
            event_publisher=event_publisher,
        )
        logger.info("Weather subagent node created (KMA API)")
    else:
        # Fallback: passthrough (날씨는 보조 정보)
        async def weather_node(state: dict[str, Any]) -> dict[str, Any]:
            logger.debug("Weather client not configured, skipping")
            return {**state, "weather_context": None}

        logger.warning("Weather subagent node using passthrough (no client)")

    # Subagent 노드: Collection Point (KECO API) - 수거함 위치 검색
    if collection_point_client is not None:
        collection_point_node = create_collection_point_node(
            collection_point_client=collection_point_client,
            event_publisher=event_publisher,
        )
        logger.info("Collection point subagent node created (KECO API)")
    else:
        # Fallback: passthrough
        async def collection_point_node(state: dict[str, Any]) -> dict[str, Any]:
            logger.warning("Collection point client not configured, using passthrough")
            return state

        logger.warning("Collection point subagent node using passthrough (no client)")

    # Subagent 노드: Image Generation (Responses API)
    if image_generator is not None:
        image_generation_node = create_image_generation_node(
            image_generator=image_generator,
            event_publisher=event_publisher,
            default_size=image_default_size,
            default_quality=image_default_quality,
        )
        logger.info("Image generation subagent node created (Responses API)")
    else:
        # Fallback: passthrough
        async def image_generation_node(state: dict[str, Any]) -> dict[str, Any]:
            logger.warning("Image generator not configured, using passthrough")
            return {
                **state,
                "image_generation_context": {
                    "success": False,
                    "error": "이미지 생성 기능이 비활성화되어 있습니다.",
                },
            }

        logger.warning("Image generation subagent node using passthrough (no client)")

    # General 노드: passthrough
    async def general_node(state: dict[str, Any]) -> dict[str, Any]:
        return state

    # Aggregator 노드 (동적 라우팅용)
    if enable_dynamic_routing:
        aggregator_node = create_aggregator_node(event_publisher)
        logger.info("Aggregator node created (for dynamic routing)")
    else:
        aggregator_node = None

    # 노드 등록
    graph.add_node("character", character_node)
    graph.add_node("location", location_node)  # 카카오맵 장소 검색
    graph.add_node("web_search", web_search_node)
    graph.add_node("bulk_waste", bulk_waste_node)  # 대형폐기물 정보
    graph.add_node("recyclable_price", recyclable_price_node)  # 재활용자원 시세
    graph.add_node("weather", weather_node)  # 날씨 정보
    graph.add_node("collection_point", collection_point_node)  # 수거함 위치
    graph.add_node("image_generation", image_generation_node)  # 이미지 생성 (Responses API)
    graph.add_node("general", general_node)

    # Aggregator 노드 등록 (동적 라우팅용)
    if aggregator_node is not None:
        graph.add_node("aggregator", aggregator_node)

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

    # 최종 목적지 결정
    # 동적 라우팅: subagents → aggregator → [summarize?] → answer
    # 정적 라우팅: subagents → [summarize?] → answer
    if enable_dynamic_routing:
        aggregator_target = "aggregator"
    else:
        aggregator_target = None

    final_before_answer = "summarize" if summarization_node is not None else "answer"

    if enable_dynamic_routing:
        # 동적 라우팅 (Send API)
        dynamic_router = create_dynamic_router(
            enable_multi_intent=enable_multi_intent,
            enable_enrichment=enable_enrichment,
            enable_conditional=True,  # state 기반 조건부 enrichment
        )

        # Router → 동적 라우팅 (list[Send] 반환)
        graph.add_conditional_edges("router", dynamic_router)

        logger.info(
            "Dynamic routing enabled",
            extra={
                "multi_intent": enable_multi_intent,
                "enrichment": enable_enrichment,
            },
        )

        # 모든 서브에이전트 노드 → aggregator
        # feedback이 활성화되면 waste_rag → feedback → aggregator
        if feedback_enabled:
            graph.add_edge("waste_rag", "feedback")
            graph.add_conditional_edges(
                "feedback",
                route_after_feedback,
                {
                    "answer": aggregator_target,
                },
            )
        else:
            graph.add_edge("waste_rag", aggregator_target)

        for node_name in ["character", "location", "web_search", "bulk_waste", "recyclable_price", "weather", "collection_point", "image_generation", "general"]:
            graph.add_edge(node_name, aggregator_target)

        # aggregator → [summarize?] → answer
        graph.add_edge("aggregator", final_before_answer)

    else:
        # 정적 라우팅 (Legacy - 단일 노드 라우팅)
        graph.add_conditional_edges(
            "router",
            route_by_intent,
            {
                "waste": "waste_rag",
                "character": "character",
                "location": "location",
                "web_search": "web_search",
                "bulk_waste": "bulk_waste",
                "recyclable_price": "recyclable_price",
                "collection_point": "collection_point",
                "image_generation": "image_generation",
                "general": "general",
            },
        )

        logger.info("Static routing enabled (legacy mode)")

        # waste_rag → feedback → [summarize?] → answer (Feedback Loop)
        if feedback_enabled:
            graph.add_edge("waste_rag", "feedback")
            graph.add_conditional_edges(
                "feedback",
                route_after_feedback,
                {
                    "answer": final_before_answer,
                },
            )
        else:
            graph.add_edge("waste_rag", final_before_answer)

        for node_name in ["character", "location", "web_search", "bulk_waste", "recyclable_price", "weather", "collection_point", "image_generation", "general"]:
            graph.add_edge(node_name, final_before_answer)

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
