import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from domains.location.api.v1.routers import api_router, health_router
from domains.location.core.constants import (
    DEFAULT_ENVIRONMENT,
    ENV_KEY_ENVIRONMENT,
    SERVICE_NAME,
    SERVICE_VERSION,
)
from domains.location.core.logging import configure_logging
from domains.location.core.tracing import (
    configure_tracing,
    instrument_fastapi,
    instrument_httpx,
    shutdown_tracing,
)
from domains.location.metrics import register_metrics

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
    shutdown_tracing()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Location API",
        description="Geospatial lookup for recycling facilities",
        version=SERVICE_VERSION,
        docs_url="/api/v1/locations/docs",
        redoc_url="/api/v1/locations/redoc",
        openapi_url="/api/v1/locations/openapi.json",
        lifespan=lifespan,
    )

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

    app.include_router(health_router)
    app.include_router(api_router)
    register_metrics(app)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
