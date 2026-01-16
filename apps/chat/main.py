"""Chat Service Main Application.

FastAPI 앱 팩토리 및 라이프사이클 관리.

분산 트레이싱 통합:
- FastAPI 자동 계측 (HTTP 요청/응답)
- HTTPX 자동 계측 (LLM API 호출)
- Redis 자동 계측 (Pub/Sub)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chat.infrastructure.persistence_postgres.mappings import start_mappers
from chat.presentation.http.controllers import chat_router
from chat.setup.config import get_settings
from chat.setup.dependencies import get_container
from chat.setup.tracing import (
    configure_tracing,
    instrument_fastapi,
    instrument_httpx,
    instrument_redis,
    shutdown_tracing,
)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# OpenTelemetry 분산 트레이싱 설정
configure_tracing()
instrument_httpx()
instrument_redis()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 라이프사이클 관리.

    Startup:
      - ORM Mapper 초기화
      - Container 초기화
      - Redis 연결 확인

    Shutdown:
      - 리소스 정리
    """
    logger.info("Chat service starting...")
    settings = get_settings()
    container = get_container()

    # Startup - ORM Mapper 초기화
    start_mappers()
    logger.info("ORM mappers initialized")

    logger.info(
        "Environment: %s, Provider: %s",
        settings.environment,
        settings.default_provider,
    )

    yield

    # Shutdown
    logger.info("Chat service shutting down...")
    await container.close()
    shutdown_tracing()


def create_app() -> FastAPI:
    """FastAPI 앱 팩토리.

    Returns:
        설정된 FastAPI 앱 인스턴스
    """
    settings = get_settings()

    app = FastAPI(
        title="Eco² Chat API",
        description="분리배출 AI 챗봇 서비스",
        version="1.0.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
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

    # 라우터 등록
    # Note: SSE는 별도 SSE Gateway에서 처리 (/api/v1/chat/{job_id}/events)
    # 참조: workloads/routing/sse-gateway/base/virtual-service.yaml
    app.include_router(chat_router, prefix="/api/v1")

    # 루트 헬스체크
    @app.get("/health")
    async def root_health():
        return {
            "status": "healthy",
            "service": settings.service_name,
            "environment": settings.environment,
        }

    return app


# 앱 인스턴스 (uvicorn용)
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "chat.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
