from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from domains.auth.api.v1.routers import api_router, health_probe_router
from domains.auth.core.exceptions import (
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Auth API",
        description="Authentication/Authorization service",
        version="0.7.3",
        docs_url="/api/v1/auth/docs",
        redoc_url="/api/v1/auth/redoc",
        openapi_url="/api/v1/auth/openapi.json",
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

    # Health 엔드포인트는 루트 레벨에 마운트 (Kubernetes probes용)
    app.include_router(health_probe_router)
    # API 엔드포인트는 /api/v1 prefix 사용
    app.include_router(api_router)
    return app


app = create_app()
