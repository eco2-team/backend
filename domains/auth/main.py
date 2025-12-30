from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from domains.auth.presentation.http.routers import api_router, health_probe_router
from domains.auth.setup.constants import (
    DEFAULT_ENVIRONMENT,
    ENV_KEY_ENVIRONMENT,
    SERVICE_NAME,
    SERVICE_VERSION,
)
from domains.auth.presentation.http.errors.handlers import (
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from domains.auth.setup.logging import configure_logging
from domains.auth.setup.tracing import (
    configure_tracing,
    instrument_fastapi,
    instrument_httpx,
    instrument_redis,
    shutdown_tracing,
)
from domains.auth.metrics import register_metrics
from domains.auth.application.services.key_manager import KeyManager

import os

# 구조화된 로깅 설정 (ECS JSON 포맷)
configure_logging()

# OpenTelemetry 분산 트레이싱 설정
environment = os.getenv(ENV_KEY_ENVIRONMENT, DEFAULT_ENVIRONMENT)
configure_tracing(
    service_name=SERVICE_NAME,
    service_version=SERVICE_VERSION,
    environment=environment,
)

# 글로벌 instrumentation (앱 생성 전)
instrument_httpx()
instrument_redis(None)  # Redis는 자동으로 모든 클라이언트 계측


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    KeyManager.ensure_keys()
    yield

    # Shutdown
    shutdown_tracing()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Auth API",
        description="Authentication/Authorization service",
        version=SERVICE_VERSION,
        docs_url="/api/v1/auth/docs",
        redoc_url="/api/v1/auth/redoc",
        openapi_url="/api/v1/auth/openapi.json",
        lifespan=lifespan,
    )

    # Add exception handlers for standardized error responses
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)

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

    # Health 엔드포인트는 루트 레벨에 마운트 (Kubernetes probes용)
    app.include_router(health_probe_router)
    # API 엔드포인트는 /api/v1 prefix 사용
    app.include_router(api_router)
    register_metrics(app)
    return app


app = create_app()
