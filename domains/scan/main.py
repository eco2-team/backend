import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from domains.scan.api.v1.endpoints import api_router, health_router
from domains.scan.core.config import get_settings
from domains.scan.core.constants import (
    DEFAULT_ENVIRONMENT,
    ENV_KEY_ENVIRONMENT,
    SERVICE_NAME,
    SERVICE_VERSION,
)
from domains.scan.core.grpc_client import close_character_client
from domains.scan.core.logging import configure_logging
from domains.scan.core.tracing import (
    configure_tracing,
    instrument_fastapi,
    instrument_httpx,
    shutdown_tracing,
)
from domains.scan.metrics import register_metrics

# 구조화된 로깅 설정 (ECS JSON 포맷)
configure_logging()

# OpenTelemetry 분산 트레이싱 설정
environment = os.getenv(ENV_KEY_ENVIRONMENT, DEFAULT_ENVIRONMENT)
configure_tracing(
    service_name=SERVICE_NAME,
    service_version=SERVICE_VERSION,
    environment=environment,
)

# 글로벌 instrumentation
instrument_httpx()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Cleanup on shutdown
    await close_character_client()
    shutdown_tracing()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Scan API",
        description="Waste classification pipeline",
        version=SERVICE_VERSION,
        docs_url="/api/v1/scan/docs",
        openapi_url="/api/v1/scan/openapi.json",
        redoc_url="/api/v1/scan/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # OpenTelemetry FastAPI instrumentation
    instrument_fastapi(app)

    app.include_router(health_router)
    app.include_router(api_router)
    register_metrics(app)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
