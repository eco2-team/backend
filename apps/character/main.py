"""Character Service Main Entry Point."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.character.presentation.http.controllers import catalog, health, reward
from apps.character.setup.config import get_settings
from apps.character.setup.database import close_redis

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """애플리케이션 라이프사이클 관리."""
    logger.info("Starting Character API service")

    # OpenTelemetry 설정
    if settings.otel_enabled:
        from domains._shared.observability.tracing import setup_tracing

        setup_tracing(settings.service_name)

    yield

    # Cleanup
    logger.info("Shutting down Character API service")
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

    # Routers
    app.include_router(health.router)
    app.include_router(catalog.router, prefix="/api/v1")
    app.include_router(reward.router, prefix="/api/v1")

    return app


app = create_app()
