"""Character Service Main Entry Point.

분산 트레이싱 통합:
- FastAPI 자동 계측 (HTTP 요청/응답)
- HTTPX 자동 계측 (외부 API 호출)
- Redis 자동 계측 (캐시)
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from character.infrastructure.observability import (
    instrument_fastapi,
    instrument_httpx,
    instrument_redis,
    setup_tracing,
    shutdown_tracing,
)
from character.presentation.http.controllers import catalog, health, reward
from character.setup.config import get_settings
from character.setup.database import close_redis

logger = logging.getLogger(__name__)
settings = get_settings()


def _init_orm_mappers() -> None:
    """ORM 매퍼 초기화."""
    from character.infrastructure.persistence_postgres.mappings import start_mappers

    try:
        start_mappers()
        logger.info("ORM mappers initialized")
    except Exception as e:
        # 이미 매핑된 경우 무시
        logger.debug(f"ORM mappers already initialized: {e}")


async def warmup_local_cache() -> None:
    """로컬 캐시 워밍업 (DB에서 캐릭터 로드).

    API 서버 시작 시 DB에서 캐릭터 목록을 로드하여
    로컬 인메모리 캐시를 초기화합니다.
    """
    try:
        from character.infrastructure.cache import get_character_cache
        from character.infrastructure.persistence_postgres import (
            SqlaCharacterReader,
        )
        from character.setup.database import async_session_factory

        cache = get_character_cache()

        # 이미 초기화되어 있으면 스킵
        if cache.is_initialized:
            logger.info("Local cache already initialized, skipping warmup")
            return

        async with async_session_factory() as session:
            reader = SqlaCharacterReader(session)
            characters = await reader.list_all()

            if characters:
                cache.set_all(list(characters))
                logger.info(
                    "Local cache warmup completed",
                    extra={"count": len(characters)},
                )
            else:
                logger.warning("Local cache warmup: no characters found in database")

    except Exception as e:
        logger.warning(
            "Local cache warmup failed (graceful degradation)",
            extra={"error": str(e)},
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """애플리케이션 라이프사이클 관리."""
    logger.info("Starting Character API service")

    # ORM 매퍼 초기화 (Imperative Mapping)
    _init_orm_mappers()

    # OpenTelemetry 설정
    if settings.otel_enabled:
        setup_tracing(settings.service_name)
        instrument_httpx()
        instrument_redis()

    # 로컬 캐시 워밍업
    await warmup_local_cache()

    # MQ Consumer 시작 (캐시 실시간 동기화)
    if settings.celery_broker_url:
        from character.infrastructure.cache import start_cache_consumer

        start_cache_consumer(settings.celery_broker_url)
        logger.info("Cache consumer started for real-time sync")

    yield

    # Cleanup
    logger.info("Shutting down Character API service")
    shutdown_tracing()

    # MQ Consumer 중지
    from character.infrastructure.cache import stop_cache_consumer

    stop_cache_consumer()

    await close_redis()


def create_app() -> FastAPI:
    """FastAPI 앱을 생성합니다."""
    app = FastAPI(
        title="Character API",
        description="캐릭터 카탈로그 및 리워드 평가 서비스",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # OpenTelemetry FastAPI instrumentation
    if settings.otel_enabled:
        instrument_fastapi(app)

    # Routers
    app.include_router(health.router)
    app.include_router(catalog.router, prefix="/api/v1")
    app.include_router(reward.router, prefix="/api/v1")

    return app


app = create_app()
