"""Scan API Main Application.

분산 트레이싱 통합:
- FastAPI 자동 계측 (HTTP 요청/응답)
- HTTPX 자동 계측 (Vision API 호출)
- Redis 자동 계측 (Streams 발행)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from scan.presentation.http.controllers import health_router, scan_router
from scan.setup.config import get_settings
from scan.setup.tracing import (
    configure_tracing,
    instrument_fastapi,
    instrument_httpx,
    instrument_redis,
    shutdown_tracing,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# OpenTelemetry 분산 트레이싱 설정
configure_tracing()
instrument_httpx()
instrument_redis()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 라이프스팬 이벤트."""
    logger.info(f"Starting {settings.service_name} v{settings.service_version}")
    yield
    logger.info(f"Shutting down {settings.service_name}")
    shutdown_tracing()


def create_app() -> FastAPI:
    """FastAPI 애플리케이션 생성."""
    app = FastAPI(
        title="Scan API",
        description="AI-powered waste classification pipeline",
        version=settings.service_version,
        docs_url="/api/v1/scan/docs",
        redoc_url="/api/v1/scan/redoc",
        openapi_url="/api/v1/scan/openapi.json",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # OpenTelemetry FastAPI instrumentation
    instrument_fastapi(app)

    # Routers
    app.include_router(health_router)
    app.include_router(scan_router, prefix="/api/v1")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
