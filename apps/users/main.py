"""Users API - FastAPI application entry point.

분산 트레이싱 통합:
- FastAPI 자동 계측 (HTTP 요청/응답)
- HTTPX 자동 계측 (외부 API 호출)
- Redis 자동 계측 (캐시)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from users.infrastructure.persistence_postgres.mappings import start_mappers
from users.presentation.http.controllers import (
    characters_router,
    health_router,
    profile_router,
)
from users.setup.config import get_settings
from users.setup.logging import setup_logging
from users.setup.tracing import (
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
    """애플리케이션 수명주기 관리."""
    # Startup
    setup_logging("DEBUG" if settings.environment == "local" else "INFO")
    logger.info(f"Starting {settings.app_name} ({settings.environment})")

    # ORM 매핑 시작
    start_mappers()
    logger.info("ORM mappings initialized")

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.app_name}")
    shutdown_tracing()


def create_app() -> FastAPI:
    """FastAPI 애플리케이션을 생성합니다."""
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="User profile and character inventory management API",
        docs_url="/api/v1/users/docs",
        openapi_url="/api/v1/users/openapi.json",
        redoc_url="/api/v1/users/redoc",
        lifespan=lifespan,
    )

    # CORS 미들웨어 (domains/my 호환)
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
    instrument_fastapi(app)

    # 라우터 등록
    app.include_router(health_router)  # /health, /ping (prefix 없음)
    app.include_router(profile_router, prefix="/api/v1/users")
    app.include_router(characters_router, prefix="/api/v1/users")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "users.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment == "local",
    )
