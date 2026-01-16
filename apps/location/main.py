"""Location API - FastAPI application entry point.

분산 트레이싱 통합:
- FastAPI 자동 계측 (HTTP 요청/응답)
- HTTPX 자동 계측 (카카오맵 API 호출)
- Redis 자동 계측 (캐시)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from location.infrastructure.observability import (
    instrument_fastapi,
    instrument_httpx,
    instrument_redis,
    setup_tracing,
    shutdown_tracing,
)
from location.presentation.http.controllers import health_router, location_router
from location.setup.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """애플리케이션 라이프사이클 관리."""
    logger.info(f"Starting {settings.service_name}")

    # OpenTelemetry 설정
    if settings.otel_enabled:
        setup_tracing(settings.service_name)
        instrument_httpx()
        instrument_redis()

    yield

    logger.info(f"Shutting down {settings.service_name}")
    shutdown_tracing()


def create_app() -> FastAPI:
    """FastAPI 애플리케이션을 생성합니다."""
    app = FastAPI(
        title="Location API",
        description="Geospatial lookup for recycling facilities",
        version="1.0.0",
        docs_url="/api/v1/locations/docs",
        openapi_url="/api/v1/locations/openapi.json",
        redoc_url="/api/v1/locations/redoc",
        lifespan=lifespan,
    )

    # CORS 미들웨어 추가
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://frontend1.dev.growbin.app",
            "https://frontend2.dev.growbin.app",
            "https://frontend.dev.growbin.app",
            "http://localhost:5173",
            "https://localhost:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # OpenTelemetry FastAPI instrumentation
    if settings.otel_enabled:
        instrument_fastapi(app)

    # 라우터 등록
    app.include_router(health_router)
    app.include_router(location_router, prefix="/api/v1")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "apps.location.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment == "development",
    )
