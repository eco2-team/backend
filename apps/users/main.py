"""Users API - FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from apps.users.infrastructure.persistence_postgres.mappings import start_mappers
from apps.users.presentation.http.controllers import (
    characters_router,
    health_router,
    profile_router,
)
from apps.users.setup.config import get_settings
from apps.users.setup.logging import setup_logging

logger = logging.getLogger(__name__)
settings = get_settings()


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

    # 라우터 등록
    app.include_router(health_router)  # /health, /ping (prefix 없음)
    app.include_router(profile_router, prefix="/api/v1/users")
    app.include_router(characters_router, prefix="/api/v1/users")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "apps.users.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment == "local",
    )
