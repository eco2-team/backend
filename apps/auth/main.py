"""Auth API Application Entry Point.

Clean Architecture 기반 Auth 서비스입니다.

분산 트레이싱 통합:
- FastAPI 자동 계측 (HTTP 요청/응답)
- HTTPX 자동 계측 (OAuth provider 호출)
- Redis 자동 계측 (세션/블랙리스트)
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from auth.presentation.http.controllers import root_router
from auth.presentation.http.errors import register_exception_handlers
from auth.setup.config import get_settings
from auth.setup.logging import setup_logging
from auth.setup.tracing import (
    configure_tracing,
    instrument_fastapi,
    instrument_httpx,
    instrument_redis,
    shutdown_tracing,
)

logger = logging.getLogger(__name__)

# OpenTelemetry 분산 트레이싱 설정
configure_tracing()
instrument_httpx()
instrument_redis()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기 관리."""
    # Startup
    logger.info("Starting Auth API (Clean Architecture)")

    # ORM 매퍼 시작
    from auth.infrastructure.persistence_postgres.mappings import start_all_mappers

    try:
        start_all_mappers()
        logger.info("ORM mappers initialized")
    except Exception as e:
        logger.warning(f"ORM mappers already initialized or error: {e}")

    yield

    # Shutdown
    logger.info("Shutting down Auth API")
    shutdown_tracing()


def create_app() -> FastAPI:
    """FastAPI 애플리케이션 팩토리."""
    settings = get_settings()

    # 로깅 설정
    setup_logging("DEBUG" if settings.environment == "local" else "INFO")

    app = FastAPI(
        title="Auth API",
        description="OAuth 인증 서비스 (Clean Architecture)",
        version="2.0.0",
        lifespan=lifespan,
    )

    # CORS 설정
    cors_origins = (
        settings.cors_origins.split(",")
        if settings.cors_origins
        else [
            "https://frontend.dev.growbin.app",
            "https://frontend1.dev.growbin.app",
            "https://frontend2.dev.growbin.app",
            "https://growbin.app",
            "http://localhost:3000",
            "http://localhost:5173",
        ]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 예외 핸들러 등록
    register_exception_handlers(app)

    # OpenTelemetry FastAPI instrumentation
    instrument_fastapi(app)

    # 라우터 등록
    app.include_router(root_router)

    # Health check (루트)
    @app.get("/health")
    async def root_health():
        return {"status": "healthy", "service": "auth-api", "version": "2.0.0"}

    return app


# 애플리케이션 인스턴스
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "auth.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
