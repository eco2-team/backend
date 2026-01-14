"""Chat Worker Dependencies - DI 팩토리.

Application Layer Use Case 조립의 핵심.
Port/Adapter 연결과 Use Case 생성 담당.

gRPC Clients (Subagent용):
- CharacterGrpcClient: Character API gRPC 호출
- LocationGrpcClient: Location API gRPC 호출

체크포인팅:
- PostgreSQL: 멀티턴 대화 히스토리 영구 저장 (Cursor 스타일)
- Redis (폴백): 단기 세션용 (TTL 24시간)

왜 gRPC (동기) vs Celery (비동기)?
- LangGraph는 asyncio 기반 오케스트레이션
- gRPC는 grpc.aio로 asyncio 네이티브 지원 (~1-100ms)
- Celery는 Fire & Forget에 적합, 결과 대기(await)에 부적합
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Literal

from redis.asyncio import Redis

# Application Layer
from chat_worker.application.commands import ProcessChatCommand
from chat_worker.application.ports import (
    LLMClientPort,
    ProgressNotifierPort,
    RetrieverPort,
)
from chat_worker.application.ports.vision import VisionModelPort
from chat_worker.application.ports.web_search import WebSearchPort
from chat_worker.application.integrations.character.ports import CharacterClientPort
from chat_worker.application.integrations.location.ports import LocationClientPort
from chat_worker.application.interaction.ports import (
    InputRequesterPort,
    InteractionStateStorePort,
)

# Infrastructure Layer
from chat_worker.infrastructure.retrieval import LocalAssetRetriever
from chat_worker.infrastructure.events import (
    RedisProgressNotifier,
    RedisStreamDomainEventBus,
)
from chat_worker.infrastructure.orchestration.langgraph import create_chat_graph
from chat_worker.infrastructure.llm import GeminiLLMClient, OpenAILLMClient
from chat_worker.infrastructure.llm.vision import (
    GeminiVisionClient,
    OpenAIVisionClient,
)
from chat_worker.infrastructure.integrations import (
    CharacterGrpcClient,
    LocationGrpcClient,
)
from chat_worker.infrastructure.integrations.web_search import DuckDuckGoSearchClient
from chat_worker.infrastructure.interaction import (
    RedisInputRequester,
    RedisInteractionStateStore,
)
from chat_worker.setup.config import get_settings

logger = logging.getLogger(__name__)


# ============================================================
# Singleton Instances
# ============================================================

_redis: Redis | None = None
_progress_notifier: ProgressNotifierPort | None = None
_domain_event_bus: RedisStreamDomainEventBus | None = None
_retriever: RetrieverPort | None = None
_character_client: CharacterClientPort | None = None
_location_client: LocationClientPort | None = None
_web_search_client: WebSearchPort | None = None
_interaction_state_store: InteractionStateStorePort | None = None
_input_requester: InputRequesterPort | None = None
_checkpointer = None  # BaseCheckpointSaver


async def get_redis() -> Redis:
    """Redis 클라이언트 싱글톤."""
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        logger.info("Redis connected: %s", settings.redis_url)
    return _redis


async def get_progress_notifier() -> ProgressNotifierPort:
    """ProgressNotifier 싱글톤 (SSE/UI 이벤트)."""
    global _progress_notifier
    if _progress_notifier is None:
        redis = await get_redis()
        _progress_notifier = RedisProgressNotifier(
            redis=redis,
            stream_prefix="chat:events",
        )
    return _progress_notifier


async def get_domain_event_bus() -> RedisStreamDomainEventBus:
    """DomainEventBus 싱글톤 (시스템 이벤트)."""
    global _domain_event_bus
    if _domain_event_bus is None:
        redis = await get_redis()
        _domain_event_bus = RedisStreamDomainEventBus(redis=redis)
    return _domain_event_bus


@lru_cache
def get_retriever() -> RetrieverPort:
    """Retriever 싱글톤."""
    return LocalAssetRetriever()


# ============================================================
# LLM Client Factory
# ============================================================


def create_llm_client(
    provider: Literal["openai", "gemini"] = "openai",
    model: str | None = None,
) -> LLMClientPort:
    """LLM 클라이언트 팩토리."""
    settings = get_settings()

    if provider == "gemini":
        return GeminiLLMClient(
            model=model or settings.gemini_default_model,
            api_key=settings.google_api_key,
        )
    else:
        return OpenAILLMClient(
            model=model or settings.openai_default_model,
            api_key=settings.openai_api_key,
        )


def create_vision_client(
    provider: Literal["openai", "gemini"] = "openai",
    model: str | None = None,
) -> VisionModelPort:
    """Vision 모델 클라이언트 팩토리."""
    settings = get_settings()

    if provider == "gemini":
        # Gemini: 멀티모달 모델
        return GeminiVisionClient(
            model=model or settings.gemini_default_model,
            api_key=settings.google_api_key,
        )
    else:
        # OpenAI: GPT-5.2-turbo 멀티모달 모델 (텍스트+이미지 통합)
        return OpenAIVisionClient(
            model=model or settings.openai_default_model,
            api_key=settings.openai_api_key,
        )


# ============================================================
# gRPC Client Factory (Subagent용)
# ============================================================


async def get_character_client() -> CharacterClientPort:
    """Character gRPC 클라이언트 싱글톤.

    Character API의 gRPC 서비스를 호출합니다.
    LangGraph의 character_subagent 노드에서 사용.

    왜 gRPC인가?
    - asyncio 네이티브 (grpc.aio)
    - 낮은 지연 시간 (~1-3ms, LocalCache)
    - 타입 안전 (Protobuf)
    """
    global _character_client
    if _character_client is None:
        settings = get_settings()
        _character_client = CharacterGrpcClient(
            host=settings.character_grpc_host,
            port=settings.character_grpc_port,
        )
        logger.info(
            "Character gRPC client created: %s:%d",
            settings.character_grpc_host,
            settings.character_grpc_port,
        )
    return _character_client


async def get_location_client() -> LocationClientPort:
    """Location gRPC 클라이언트 싱글톤.

    Location API의 gRPC 서비스를 호출합니다.
    LangGraph의 location_subagent 노드에서 사용.

    왜 gRPC인가?
    - asyncio 네이티브 (grpc.aio)
    - 낮은 지연 시간 (~100ms, PostGIS)
    - 타입 안전 (Protobuf)
    """
    global _location_client
    if _location_client is None:
        settings = get_settings()
        _location_client = LocationGrpcClient(
            host=settings.location_grpc_host,
            port=settings.location_grpc_port,
        )
        logger.info(
            "Location gRPC client created: %s:%d",
            settings.location_grpc_host,
            settings.location_grpc_port,
        )
    return _location_client


# ============================================================
# Web Search Client Factory
# ============================================================


def get_web_search_client() -> WebSearchPort:
    """웹 검색 클라이언트 싱글톤.

    웹 검색 서브에이전트에서 사용.
    기본: DuckDuckGo (무료, API 키 불필요)
    선택: Tavily (LLM 최적화, API 키 필요)

    환경변수:
    - TAVILY_API_KEY: 설정 시 Tavily 사용
    """
    global _web_search_client
    if _web_search_client is None:
        settings = get_settings()

        # Tavily API 키가 있으면 Tavily 사용
        if settings.tavily_api_key:
            from chat_worker.infrastructure.integrations.web_search.tavily import (
                TavilySearchClient,
            )

            _web_search_client = TavilySearchClient(api_key=settings.tavily_api_key)
            logger.info("Tavily web search client created (LLM-optimized)")
        else:
            # 기본: DuckDuckGo
            _web_search_client = DuckDuckGoSearchClient()
            logger.info("DuckDuckGo web search client created (free, no API key)")

    return _web_search_client


# ============================================================
# Interaction Factory (Human-in-the-Loop)
# ============================================================


async def get_interaction_state_store() -> InteractionStateStorePort:
    """InteractionStateStore 싱글톤 (HITL 상태 저장).

    SoT 분리:
    - InputRequester: 이벤트 발행만
    - StateStore: 상태 저장/조회만
    """
    global _interaction_state_store
    if _interaction_state_store is None:
        redis = await get_redis()
        _interaction_state_store = RedisInteractionStateStore(redis)
        logger.info("RedisInteractionStateStore created")
    return _interaction_state_store


async def get_input_requester() -> InputRequesterPort:
    """InputRequester 싱글톤 (HITL 입력 요청).

    Human-in-the-Loop 패턴 (Blocking Wait 제거):
    - Worker가 needs_input 이벤트 발행
    - 상태 저장 후 파이프라인 일시중단
    - Frontend가 입력 수집 후 POST /chat/{job_id}/input
    - Presentation에서 상태 복원 → 파이프라인 재개

    Clean Architecture:
    - Port: InputRequesterPort (application/interaction/ports/)
    - Adapter: RedisInputRequester (infrastructure/interaction/)
    """
    global _input_requester
    if _input_requester is None:
        progress_notifier = await get_progress_notifier()
        state_store = await get_interaction_state_store()
        _input_requester = RedisInputRequester(
            progress_notifier=progress_notifier,
            state_store=state_store,
        )
        logger.info("RedisInputRequester created (Human-in-the-Loop enabled)")
    return _input_requester


# ============================================================
# Checkpointer Factory (멀티턴 대화)
# ============================================================


async def get_checkpointer():
    """LangGraph 체크포인터 싱글톤.

    멀티턴 대화 컨텍스트를 저장합니다.

    Cache-Aside 패턴:
    - L1: Redis (빠름, TTL 24시간) - Hot session
    - L2: PostgreSQL (영구) - Cold session, 장기 보존

    조회 플로우:
    1. Redis 캐시 조회 (~1ms)
    2. Cache Miss → PostgreSQL 조회 (~5-10ms)
    3. 결과를 Redis에 캐싱 (warm-up)

    Scan vs Chat:
    - Scan: Stateless Reducer + Redis (단일 요청)
    - Chat: Cache-Aside + PostgreSQL (멀티턴 대화)
    """
    global _checkpointer
    if _checkpointer is None:
        settings = get_settings()

        if settings.postgres_url:
            # Cache-Aside PostgreSQL 체크포인터 (Redis L1 + PostgreSQL L2)
            from chat_worker.infrastructure.langgraph.checkpointer import (
                create_cached_postgres_checkpointer,
            )

            try:
                redis = await get_redis()
                _checkpointer = await create_cached_postgres_checkpointer(
                    conn_string=settings.postgres_url,
                    redis=redis,
                    cache_ttl=86400,  # 24시간
                )
                logger.info("CachedPostgresSaver initialized (Redis L1 + PostgreSQL L2)")
            except Exception as e:
                logger.warning(
                    "CachedPostgresSaver failed, falling back to Redis only: %s", e
                )
                # Redis 폴백
                from chat_worker.infrastructure.langgraph.checkpointer import (
                    create_redis_checkpointer,
                )

                _checkpointer = await create_redis_checkpointer(
                    settings.redis_url,
                    ttl=86400,  # 24시간
                )
        else:
            # Redis 체크포인터 (단기 세션)
            from chat_worker.infrastructure.langgraph.checkpointer import (
                create_redis_checkpointer,
            )

            _checkpointer = await create_redis_checkpointer(
                settings.redis_url,
                ttl=86400,
            )
            logger.info("Redis checkpointer initialized (no PostgreSQL configured)")

    return _checkpointer


# ============================================================
# LangGraph Factory
# ============================================================


async def get_chat_graph(
    provider: Literal["openai", "gemini"] = "openai",
    model: str | None = None,
):
    """Chat LangGraph 파이프라인 생성.

    Intent-Routed Workflow with Subagent 패턴.
    체크포인터로 멀티턴 대화 컨텍스트 유지.

    ```
    START → intent → [vision?] → router
                                   │
                  ┌────────┬───────┼───────┬────────┬────────┐
                  ▼        ▼       ▼       ▼        ▼        ▼
               waste   character location web_search general
               (RAG)   (gRPC)   (gRPC)   (DDG)   (passthrough)
                  │        │       │       │        │
                  └────────┴───────┴───────┴────────┘
                                   │
                                   ▼
                                answer → END
    ```
    """
    llm = create_llm_client(provider, model)
    vision_model = create_vision_client(provider, model)
    retriever = get_retriever()
    progress_notifier = await get_progress_notifier()
    character_client = await get_character_client()
    location_client = await get_location_client()
    web_search_client = get_web_search_client()
    input_requester = await get_input_requester()
    checkpointer = await get_checkpointer()

    return create_chat_graph(
        llm=llm,
        retriever=retriever,
        event_publisher=progress_notifier,
        vision_model=vision_model,
        character_client=character_client,
        location_client=location_client,
        web_search_client=web_search_client,
        input_requester=input_requester,
        checkpointer=checkpointer,
    )


# ============================================================
# Command Factory (CQRS)
# ============================================================


async def get_process_chat_command(
    provider: Literal["openai", "gemini"] = "openai",
    model: str | None = None,
) -> ProcessChatCommand:
    """ProcessChatCommand 생성 (CQRS - Command).

    Application Layer의 Command를 조립.
    Port와 Infrastructure를 연결.

    ```
    ProcessChatCommand
        │
        ├── ChatPipelinePort (LangGraph)
        │       │
        │       ├── LLMClientPort (OpenAI/Gemini)
        │       ├── RetrieverPort (LocalJSON)
        │       └── ProgressNotifierPort (Redis)
        │
        └── ProgressNotifierPort (Redis)
    ```
    """
    settings = get_settings()
    actual_provider = provider or settings.default_provider

    pipeline = await get_chat_graph(actual_provider, model)
    progress_notifier = await get_progress_notifier()

    return ProcessChatCommand(
        pipeline=pipeline,
        event_publisher=progress_notifier,
    )


# ============================================================
# Cleanup
# ============================================================


async def cleanup():
    """리소스 정리."""
    global _redis, _character_client, _location_client, _checkpointer
    global _progress_notifier, _domain_event_bus, _interaction_state_store, _input_requester

    # 체크포인터 종료
    if _checkpointer and hasattr(_checkpointer, "close"):
        await _checkpointer.close()
        _checkpointer = None
        logger.info("Checkpointer closed")

    # gRPC 클라이언트 종료
    if _character_client and hasattr(_character_client, "close"):
        await _character_client.close()
        _character_client = None
        logger.info("Character gRPC client closed")

    if _location_client and hasattr(_location_client, "close"):
        await _location_client.close()
        _location_client = None
        logger.info("Location gRPC client closed")

    # Redis 종료
    if _redis:
        await _redis.close()
        _redis = None
        logger.info("Redis disconnected")
