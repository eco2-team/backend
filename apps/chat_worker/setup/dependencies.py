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
from chat_worker.application.ports.cache import CachePort
from chat_worker.application.ports.character_client import CharacterClientPort
from chat_worker.application.ports.input_requester import InputRequesterPort
from chat_worker.application.ports.interaction_state_store import (
    InteractionStateStorePort,
)
from chat_worker.application.ports.kakao_local_client import KakaoLocalClientPort
from chat_worker.application.ports.location_client import LocationClientPort
from chat_worker.application.ports.metrics import MetricsPort
from chat_worker.application.ports.vision import VisionModelPort
from chat_worker.application.ports.image_generator import ImageGeneratorPort
from chat_worker.application.ports.weather_client import WeatherClientPort
from chat_worker.application.ports.web_search import WebSearchPort
from chat_worker.application.ports.bulk_waste_client import BulkWasteClientPort
from chat_worker.application.ports.recyclable_price_client import (
    RecyclablePriceClientPort,
)
from chat_worker.application.ports.collection_point_client import (
    CollectionPointClientPort,
)
from chat_worker.infrastructure.assets.prompt_loader import get_prompt_loader
from chat_worker.infrastructure.cache import RedisCacheAdapter
from chat_worker.infrastructure.events import (
    RedisProgressNotifier,
    RedisStreamDomainEventBus,
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
from chat_worker.infrastructure.llm import (
    GeminiLLMClient,
    LangChainLLMAdapter,
    LangChainOpenAIRunnable,
    OpenAILLMClient,
)
from chat_worker.infrastructure.llm.vision import (
    GeminiVisionClient,
    OpenAIVisionClient,
)
from chat_worker.infrastructure.metrics import (
    NoOpMetricsAdapter,
    PrometheusMetricsAdapter,
)
from chat_worker.infrastructure.orchestration.langgraph import create_chat_graph

# Infrastructure Layer
from chat_worker.infrastructure.retrieval import TagBasedRetriever
from chat_worker.setup.config import get_settings

logger = logging.getLogger(__name__)


# ============================================================
# Singleton Instances
# ============================================================

_redis: Redis | None = None
_redis_streams: Redis | None = None  # 이벤트 스트리밍 전용 (event-router와 동일)
_progress_notifier: ProgressNotifierPort | None = None
_domain_event_bus: RedisStreamDomainEventBus | None = None
_retriever: RetrieverPort | None = None
_character_client: CharacterClientPort | None = None
_location_client: LocationClientPort | None = None
_kakao_local_client: KakaoLocalClientPort | None = None
_web_search_client: WebSearchPort | None = None
_weather_client: WeatherClientPort | None = None
_bulk_waste_client: BulkWasteClientPort | None = None
_recyclable_price_client: RecyclablePriceClientPort | None = None
_collection_point_client: CollectionPointClientPort | None = None
_interaction_state_store: InteractionStateStorePort | None = None
_input_requester: InputRequesterPort | None = None
_checkpointer = None  # BaseCheckpointSaver
_cache: CachePort | None = None
_metrics: MetricsPort | None = None
_image_generator: ImageGeneratorPort | None = None


async def get_redis() -> Redis:
    """Redis 클라이언트 싱글톤 (기본 - 캐시, Pub/Sub 등)."""
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


async def get_redis_streams() -> Redis:
    """Redis Streams 클라이언트 싱글톤 (이벤트 스트리밍 전용).

    event-router와 동일한 Redis를 바라봐야 함.
    설정되지 않으면 기본 redis_url 사용 (로컬 개발용).
    """
    global _redis_streams
    if _redis_streams is None:
        settings = get_settings()
        # redis_streams_url이 설정되면 사용, 아니면 redis_url 폴백
        streams_url = settings.redis_streams_url or settings.redis_url
        _redis_streams = Redis.from_url(
            streams_url,
            encoding="utf-8",
            decode_responses=True,
        )
        logger.info("Redis Streams connected: %s", streams_url)
    return _redis_streams


async def get_progress_notifier() -> ProgressNotifierPort:
    """ProgressNotifier 싱글톤 (SSE/UI 이벤트).

    Redis Streams로 이벤트 발행 → event-router가 소비.
    redis_streams_url을 사용해야 event-router와 동일한 Redis를 바라봄.
    """
    global _progress_notifier
    if _progress_notifier is None:
        redis = await get_redis_streams()
        _progress_notifier = RedisProgressNotifier(redis=redis)
    return _progress_notifier


async def get_domain_event_bus() -> RedisStreamDomainEventBus:
    """DomainEventBus 싱글톤 (시스템 이벤트).

    Redis Streams로 이벤트 발행 → event-router가 소비.
    """
    global _domain_event_bus
    if _domain_event_bus is None:
        redis = await get_redis_streams()
        _domain_event_bus = RedisStreamDomainEventBus(redis=redis)
    return _domain_event_bus


@lru_cache
def get_retriever() -> RetrieverPort:
    """Retriever 싱글톤 (TagBasedRetriever 사용).

    Anthropic Contextual Retrieval 패턴 적용:
    - item_class_list.yaml: 품목 매칭
    - situation_tags.yaml: 상황 태그 매칭
    """
    return TagBasedRetriever()


# ============================================================
# Cache Factory (Clean Architecture)
# ============================================================


async def get_cache() -> CachePort:
    """CachePort 싱글톤.

    Application Layer는 CachePort만 알고,
    실제 구현(Redis)은 Infrastructure에서 제공.
    """
    global _cache
    if _cache is None:
        redis = await get_redis()
        _cache = RedisCacheAdapter(redis, key_prefix="chat:cache:")
        logger.info("RedisCacheAdapter created")
    return _cache


# ============================================================
# Metrics Factory (Clean Architecture)
# ============================================================


def get_metrics() -> MetricsPort:
    """MetricsPort 싱글톤.

    Application Layer는 MetricsPort만 알고,
    실제 구현(Prometheus)은 Infrastructure에서 제공.

    테스트 환경에서는 NoOpMetricsAdapter로 교체 가능.
    """
    global _metrics
    if _metrics is None:
        try:
            _metrics = PrometheusMetricsAdapter()
            logger.info("PrometheusMetricsAdapter created")
        except ImportError:
            _metrics = NoOpMetricsAdapter()
            logger.warning("Prometheus not available, using NoOpMetricsAdapter")
    return _metrics


# ============================================================
# LLM Client Factory
# ============================================================


def create_llm_client(
    provider: Literal["openai", "google"] = "openai",
    model: str | None = None,
    enable_token_streaming: bool = True,
) -> LLMClientPort:
    """LLM 클라이언트 팩토리.

    Args:
        provider: LLM 프로바이더 ("openai" 또는 "google")
        model: 모델명 (None이면 기본값 사용)
        enable_token_streaming: LangGraph stream_mode="messages" 토큰 스트리밍 활성화

    Returns:
        LLMClientPort 구현체

    Token Streaming:
        enable_token_streaming=True (기본):
        - OpenAI: LangChainLLMAdapter + LangChainOpenAIRunnable 사용
        - LangGraph stream_mode="messages"가 토큰을 캡처하여 SSE로 전달

        enable_token_streaming=False:
        - 기존 OpenAILLMClient 사용 (순수 SDK)
        - 토큰 스트리밍 미지원 (done 이벤트에 전체 답변)
    """
    settings = get_settings()

    if provider == "google":
        # Google Gemini (토큰 스트리밍 미지원)
        return GeminiLLMClient(
            model=model or settings.gemini_default_model,
            api_key=settings.google_api_key,
        )
    else:
        # OpenAI
        actual_model = model or settings.openai_default_model

        if enable_token_streaming:
            # LangChain Runnable 기반 - stream_mode="messages" 토큰 캡처 지원
            runnable = LangChainOpenAIRunnable(
                model=actual_model,
                api_key=settings.openai_api_key,
            )
            return LangChainLLMAdapter(runnable)
        else:
            # 순수 OpenAI SDK - 토큰 스트리밍 미지원
            return OpenAILLMClient(
                model=actual_model,
                api_key=settings.openai_api_key,
            )


def create_vision_client(
    provider: Literal["openai", "google"] = "openai",
    model: str | None = None,
) -> VisionModelPort:
    """Vision 모델 클라이언트 팩토리."""
    settings = get_settings()

    if provider == "google":
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
# Image Generator Factory (Provider 통일)
# ============================================================


def get_image_generator() -> ImageGeneratorPort | None:
    """이미지 생성 클라이언트 싱글톤.

    default_provider 설정에 따라 적합한 이미지 생성기 선택.
    enable_image_generation=True일 때만 활성화 (비용 발생).

    Provider별 이미지 생성:
    - openai: OpenAI Responses API (gpt-image-1.5)
    - google: Gemini Native Image Generation (gemini-3-pro-image-preview)

    환경변수:
    - CHAT_WORKER_ENABLE_IMAGE_GENERATION: True로 설정 시 활성화
    - CHAT_WORKER_DEFAULT_PROVIDER: 이미지 생성 Provider 결정
    """
    global _image_generator
    if _image_generator is None:
        settings = get_settings()

        if not settings.enable_image_generation:
            logger.info("Image generation disabled (enable_image_generation=False)")
            return None

        provider = settings.default_provider

        if provider == "openai":
            if not settings.openai_api_key:
                logger.warning("Image generation disabled (no OpenAI API key)")
                return None

            from chat_worker.infrastructure.llm.image_generator import (
                OpenAIResponsesImageGenerator,
            )

            _image_generator = OpenAIResponsesImageGenerator(
                model=settings.image_generation_model,
                api_key=settings.openai_api_key,
                default_size=settings.image_generation_default_size,
                default_quality=settings.image_generation_default_quality,
            )
            logger.info(
                "OpenAI Image Generator created (model=%s)",
                settings.image_generation_model,
            )

        elif provider == "google":
            if not settings.google_api_key:
                logger.warning("Image generation disabled (no Google API key)")
                return None

            from chat_worker.infrastructure.llm.image_generator import (
                GeminiNativeImageGenerator,
            )

            _image_generator = GeminiNativeImageGenerator(
                model="gemini-3-pro-image-preview",
                api_key=settings.google_api_key,
            )
            logger.info("Gemini Image Generator created (model=gemini-3-pro-image-preview)")

        else:
            logger.warning("Unknown provider for image generation: %s", provider)
            return None

    return _image_generator


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
# Kakao Local Client Factory (장소 검색)
# ============================================================


def get_kakao_local_client() -> KakaoLocalClientPort | None:
    """카카오 로컬 클라이언트 싱글톤.

    카카오 로컬 API를 사용한 장소 검색.
    API 키가 없으면 None 반환 (선택적 기능).

    환경변수:
    - CHAT_WORKER_KAKAO_REST_API_KEY: 카카오 REST API 키

    참고:
    - https://developers.kakao.com/docs/latest/ko/local/dev-guide
    - KakaoMap 설정 ON 필요 (2024년 12월 정책 변경)
    """
    global _kakao_local_client
    if _kakao_local_client is None:
        settings = get_settings()

        if settings.kakao_rest_api_key:
            from chat_worker.infrastructure.integrations.kakao import (
                KakaoLocalHttpClient,
            )

            _kakao_local_client = KakaoLocalHttpClient(
                api_key=settings.kakao_rest_api_key,
                timeout=settings.kakao_api_timeout,
            )
            logger.info("Kakao Local HTTP client created")
        else:
            logger.warning("KAKAO_REST_API_KEY not set, Kakao Local search disabled")
            return None

    return _kakao_local_client


# ============================================================
# Weather Client Factory (기상청 단기예보)
# ============================================================


def get_weather_client() -> WeatherClientPort | None:
    """기상청 날씨 클라이언트 싱글톤.

    기상청 단기예보 API를 사용한 현재 날씨/예보 조회.
    API 키가 없으면 None 반환 (선택적 기능).

    환경변수:
    - CHAT_WORKER_KMA_API_KEY: 공공데이터포털 인증키

    참고:
    - https://www.data.go.kr/data/15084084/openapi.do
    """
    global _weather_client
    if _weather_client is None:
        settings = get_settings()

        if settings.kma_api_key:
            from chat_worker.infrastructure.integrations.kma import (
                KmaWeatherHttpClient,
            )

            _weather_client = KmaWeatherHttpClient(
                api_key=settings.kma_api_key,
                timeout=settings.kma_api_timeout,
            )
            logger.info("KMA Weather HTTP client created")
        else:
            logger.warning("KMA_API_KEY not set, weather feature disabled")
            return None

    return _weather_client


# ============================================================
# Bulk Waste Client Factory (대형폐기물 정보)
# ============================================================


def get_bulk_waste_client() -> BulkWasteClientPort | None:
    """대형폐기물 클라이언트 싱글톤.

    행정안전부 생활쓰레기배출정보 API를 사용한 대형폐기물 정보 조회.
    API 키가 없으면 None 반환 (선택적 기능).

    환경변수:
    - CHAT_WORKER_MOIS_WASTE_API_KEY: 공공데이터포털 인증키

    참고:
    - https://www.data.go.kr/data/15155080/openapi.do
    """
    global _bulk_waste_client
    if _bulk_waste_client is None:
        settings = get_settings()

        if settings.mois_waste_api_key:
            from chat_worker.infrastructure.integrations.bulk_waste import (
                MoisWasteInfoHttpClient,
            )

            _bulk_waste_client = MoisWasteInfoHttpClient(
                api_key=settings.mois_waste_api_key,
                timeout=settings.mois_waste_api_timeout,
            )
            logger.info("MOIS Bulk Waste HTTP client created")
        else:
            logger.warning("MOIS_WASTE_API_KEY not set, bulk waste feature disabled")
            return None

    return _bulk_waste_client


# ============================================================
# Recyclable Price Client Factory (재활용자원 시세)
# ============================================================


def get_recyclable_price_client() -> RecyclablePriceClientPort:
    """재활용자원 시세 클라이언트 싱글톤.

    한국환경공단 재활용가능자원 가격조사 데이터 기반.
    로컬 파일(YAML) 기반 구현 (API 없이 월 1회 갱신).

    데이터 소스:
    - https://www.data.go.kr/data/3076421/fileData.do
    - 매월 10일경 갱신

    참고:
    - https://www.recycling-info.or.kr/sds/marketIndex.do
    """
    global _recyclable_price_client
    if _recyclable_price_client is None:
        from chat_worker.infrastructure.integrations.recyclable_price import (
            LocalRecyclablePriceClient,
        )

        _recyclable_price_client = LocalRecyclablePriceClient()
        logger.info("Local Recyclable Price client created")

    return _recyclable_price_client


# ============================================================
# Collection Point Client Factory (수거함 위치)
# ============================================================


def get_collection_point_client() -> CollectionPointClientPort | None:
    """수거함 위치 클라이언트 싱글톤.

    한국환경공단 폐전자제품 수거함 위치정보 API 사용.
    API 키가 없으면 None 반환 (선택적 기능).

    환경변수:
    - CHAT_WORKER_KECO_API_KEY: 공공데이터포털 인증키

    참고:
    - https://www.data.go.kr/data/15106385/fileData.do
    """
    global _collection_point_client
    if _collection_point_client is None:
        settings = get_settings()

        if settings.keco_api_key:
            from chat_worker.infrastructure.integrations.keco import (
                KecoCollectionPointClient,
            )

            _collection_point_client = KecoCollectionPointClient(
                api_key=settings.keco_api_key,
                timeout=settings.keco_api_timeout,
            )
            logger.info("KECO Collection Point HTTP client created")
        else:
            logger.warning("KECO_API_KEY not set, collection point feature disabled")
            return None

    return _collection_point_client


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
        redis = await get_redis()
        _input_requester = RedisInputRequester(redis=redis)
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
            from chat_worker.infrastructure.orchestration.langgraph.checkpointer import (
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
                logger.warning("CachedPostgresSaver failed, falling back to Redis only: %s", e)
                # Redis 폴백
                from chat_worker.infrastructure.orchestration.langgraph.checkpointer import (
                    create_redis_checkpointer,
                )

                _checkpointer = await create_redis_checkpointer(
                    settings.redis_url,
                    ttl=86400,  # 24시간
                )
        else:
            # Redis 체크포인터 (단기 세션)
            from chat_worker.infrastructure.orchestration.langgraph.checkpointer import (
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
    provider: Literal["openai", "google"] = "openai",
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
               (RAG)   (gRPC)   (Kakao)   (DDG)   (passthrough)
                  │        │       │       │        │
                  └────────┴───────┴───────┴────────┘
                                   │
                                   ▼
                                answer → END
    ```
    """
    settings = get_settings()
    llm = create_llm_client(provider, model)
    vision_model = create_vision_client(provider, model)
    retriever = get_retriever()
    prompt_loader = get_prompt_loader()  # 프롬프트 로더
    cache = await get_cache()  # P2: Intent 캐싱용 (CachePort)
    progress_notifier = await get_progress_notifier()
    character_client = await get_character_client()
    location_client = await get_location_client()
    kakao_client = get_kakao_local_client()  # 카카오 장소 검색
    web_search_client = get_web_search_client()
    bulk_waste_client = get_bulk_waste_client()  # 대형폐기물 정보
    recyclable_price_client = get_recyclable_price_client()  # 재활용자원 시세
    weather_client = get_weather_client()  # 날씨 정보 (기상청 API)
    collection_point_client = get_collection_point_client()  # 수거함 위치 (KECO API)
    image_generator = get_image_generator()  # 이미지 생성 (Responses API)
    input_requester = await get_input_requester()
    checkpointer = await get_checkpointer()

    return create_chat_graph(
        llm=llm,
        retriever=retriever,
        event_publisher=progress_notifier,
        prompt_loader=prompt_loader,  # 프롬프트 로더 주입
        vision_model=vision_model,
        character_client=character_client,
        location_client=location_client,
        kakao_client=kakao_client,  # 카카오 장소 검색 (place_search intent)
        web_search_client=web_search_client,
        bulk_waste_client=bulk_waste_client,  # 대형폐기물 정보 (행정안전부 API)
        recyclable_price_client=recyclable_price_client,  # 재활용자원 시세 (한국환경공단)
        weather_client=weather_client,  # 날씨 정보 (기상청 API)
        collection_point_client=collection_point_client,  # 수거함 위치 (KECO API)
        image_generator=image_generator,  # 이미지 생성 (Responses API)
        image_default_size=settings.image_generation_default_size,
        image_default_quality=settings.image_generation_default_quality,
        cache=cache,  # P2: Intent 캐싱 (CachePort)
        input_requester=input_requester,
        checkpointer=checkpointer,
        enable_summarization=settings.enable_summarization,  # Multi-turn 컨텍스트 압축
        summarization_model=settings.openai_default_model,  # 동적 설정: context-output 트리거
        max_tokens_before_summary=settings.max_tokens_before_summary,  # None이면 동적 계산
        max_summary_tokens=settings.max_summary_tokens,  # None이면 동적 계산
        keep_recent_messages=settings.keep_recent_messages,  # None이면 동적 계산
        # Dynamic routing 활성화 (Channel Separation + Priority Scheduling 적용됨)
        # ChatState Annotated Reducer로 Send API 병렬 실행 안전
        enable_dynamic_routing=True,
    )


# ============================================================
# Command Factory (CQRS)
# ============================================================


async def get_process_chat_command(
    provider: Literal["openai", "google"] = "openai",
    model: str | None = None,
) -> ProcessChatCommand:
    """ProcessChatCommand 생성 (CQRS - Command).

    Application Layer의 Command를 조립.
    Port와 Infrastructure를 연결.

    Event-First Architecture:
    - 메시지 영속화는 done 이벤트에 persistence 데이터 포함
    - DB Consumer가 Redis Streams에서 소비하여 PostgreSQL 저장
    - RabbitMQ 의존성 제거됨

    Telemetry (LangSmith OTEL):
    - LangGraph run config 생성 (run_name, tags, metadata)
    - OTEL 내보내기 활성화 시 Jaeger에서 추적 가능

    ```
    ProcessChatCommand
        │
        ├── ChatPipelinePort (LangGraph)
        │       │
        │       ├── LLMClientPort (OpenAI/Gemini)
        │       ├── RetrieverPort (LocalJSON)
        │       └── ProgressNotifierPort (Redis)
        │
        ├── ProgressNotifierPort (Redis)
        │       │
        │       └── done 이벤트 (persistence 데이터 포함)
        │               │
        │               └── DB Consumer → PostgreSQL
        │
        └── TelemetryConfigPort (LangSmith OTEL)
    ```
    """
    settings = get_settings()
    actual_provider = provider or settings.default_provider

    pipeline = await get_chat_graph(actual_provider, model)
    progress_notifier = await get_progress_notifier()
    metrics = get_metrics()  # MetricsPort

    # LangSmith OTEL Telemetry (optional)
    telemetry = None
    try:
        from chat_worker.setup.langsmith import TelemetryConfig

        telemetry = TelemetryConfig()
    except ImportError:
        pass

    return ProcessChatCommand(
        pipeline=pipeline,
        progress_notifier=progress_notifier,
        metrics=metrics,
        telemetry=telemetry,
        provider=actual_provider,
    )


# ============================================================
# Cleanup
# ============================================================


async def cleanup():
    """리소스 정리."""
    global _redis, _redis_streams, _character_client, _location_client, _kakao_local_client, _weather_client, _bulk_waste_client, _collection_point_client, _checkpointer
    global _progress_notifier, _domain_event_bus, _interaction_state_store, _input_requester, _image_generator

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

    # Kakao Local HTTP 클라이언트 종료
    if _kakao_local_client and hasattr(_kakao_local_client, "close"):
        await _kakao_local_client.close()
        _kakao_local_client = None
        logger.info("Kakao Local HTTP client closed")

    # KMA Weather HTTP 클라이언트 종료
    if _weather_client and hasattr(_weather_client, "close"):
        await _weather_client.close()
        _weather_client = None
        logger.info("KMA Weather HTTP client closed")

    # MOIS Bulk Waste HTTP 클라이언트 종료
    if _bulk_waste_client and hasattr(_bulk_waste_client, "close"):
        await _bulk_waste_client.close()
        _bulk_waste_client = None
        logger.info("MOIS Bulk Waste HTTP client closed")

    # KECO Collection Point HTTP 클라이언트 종료
    if _collection_point_client and hasattr(_collection_point_client, "close"):
        await _collection_point_client.close()
        _collection_point_client = None
        logger.info("KECO Collection Point HTTP client closed")

    # Image Generator 정리
    if _image_generator is not None:
        _image_generator = None
        logger.info("Image generator cleared")

    # Redis 종료
    if _redis:
        await _redis.close()
        _redis = None
        logger.info("Redis disconnected")

    # Redis Streams 종료
    if _redis_streams:
        await _redis_streams.close()
        _redis_streams = None
        logger.info("Redis Streams disconnected")
