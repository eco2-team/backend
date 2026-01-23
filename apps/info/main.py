"""Info Service Application.

환경/에너지/AI 뉴스 정보 서비스.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from info.presentation.http import router
from info.presentation.http.errors import register_exception_handlers
from info.setup.config import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    settings = get_settings()
    logger.info(
        "Info service starting",
        extra={
            "redis_url": (
                settings.redis_url.split("@")[-1]
                if "@" in settings.redis_url
                else settings.redis_url
            ),
            "cache_ttl": settings.news_cache_ttl,
            "naver_enabled": bool(settings.naver_client_id),
            "newsdata_enabled": bool(settings.newsdata_api_key),
        },
    )
    yield
    logger.info("Info service shutting down")


def create_app() -> FastAPI:
    """FastAPI 애플리케이션 팩토리."""
    settings = get_settings()

    app = FastAPI(
        title="Eco² Info Service",
        description="환경, 에너지, AI 관련 뉴스 정보 서비스",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 예외 핸들러 등록
    register_exception_handlers(app)

    # Router
    app.include_router(router)

    return app


# Uvicorn entrypoint
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "info.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
