"""SSE Gateway - 중앙 Consumer + Memory Fan-out.

서비스 특성:
- workers=1 (프로세스 1개, Pod 스케일링)
- 단일 Redis Stream Consumer
- Memory Fan-out to SSE Clients
- Long-lived Connections

참조: docs/blogs/async/31-sse-fanout-optimization.md
"""

import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sse_gateway.api.v1.stream import router as stream_router
from sse_gateway.config import get_settings
from sse_gateway.core.broadcast_manager import SSEBroadcastManager
from sse_gateway.core.tracing import (
    configure_tracing,
    instrument_fastapi,
    instrument_redis,
    shutdown_tracing,
)
from sse_gateway.metrics import register_metrics

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Logging 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)

# OpenTelemetry 분산 트레이싱 설정
configure_tracing()
instrument_redis()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Lifespan
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """앱 생명주기 관리."""
    logger.info("sse_gateway_starting")

    # BroadcastManager 초기화
    await SSEBroadcastManager.get_instance()

    logger.info("sse_gateway_started")

    yield

    # 종료
    logger.info("sse_gateway_shutting_down")
    await SSEBroadcastManager.shutdown()
    shutdown_tracing()
    logger.info("sse_gateway_stopped")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FastAPI App
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

app = FastAPI(
    title="SSE Gateway",
    description="Real-time SSE event streaming service",
    version=settings.service_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS - credentials 사용 시 특정 origin 필요
ALLOWED_ORIGINS = [
    "https://frontend1.dev.growbin.app",
    "https://frontend2.dev.growbin.app",
    "https://frontend.dev.growbin.app",
    "https://api.dev.growbin.app",
    "http://localhost:5173",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

# Prometheus metrics
register_metrics(app)

# OpenTelemetry FastAPI instrumentation
instrument_fastapi(app)

# Routers
app.include_router(stream_router, prefix="/api/v1")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Health Endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@app.get("/health", tags=["Health"])
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/ready", tags=["Health"])
async def ready() -> dict[str, str | int]:
    """Readiness probe."""
    manager = await SSEBroadcastManager.get_instance()
    return {
        "status": "ok",
        "active_jobs": manager.active_job_count,
        "total_subscribers": manager.total_subscriber_count,
    }


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "service": "sse-gateway",
        "version": settings.service_version,
        "status": "running",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        workers=1,  # 단일 프로세스 (중앙 Consumer 유지)
        log_level=settings.log_level.lower(),
    )
