"""Scan API Main Application."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from scan.presentation.http.controllers import health_router, scan_router
from scan.setup.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 라이프스팬 이벤트."""
    logger.info(f"Starting {settings.service_name} v{settings.service_version}")
    yield
    logger.info(f"Shutting down {settings.service_name}")


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

    # Routers
    app.include_router(health_router)
    app.include_router(scan_router, prefix="/api/v1")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
