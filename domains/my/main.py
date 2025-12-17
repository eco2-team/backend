from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:  # pragma: no cover - exercised during runtime/CI in different layouts
    from domains.my.api.v1.routers import api_router, health_router
    from domains.my.core.constants import SERVICE_VERSION
    from domains.my.core.logging import configure_logging
    from domains.my.metrics import register_metrics
except ModuleNotFoundError:  # local/CI pytest runs with service dir on PYTHONPATH
    current_dir = Path(__file__).resolve().parent
    if str(current_dir) not in sys.path:
        sys.path.append(str(current_dir))
    from api.v1.routers import api_router, health_router
    from core.config import SERVICE_VERSION
    from core.logging import configure_logging
    from metrics import register_metrics

# 구조화된 로깅 설정 (ECS JSON 포맷)
configure_logging()


def create_app() -> FastAPI:
    app = FastAPI(
        title="My API",
        description="User profile and rewards service",
        version=SERVICE_VERSION,
        docs_url="/api/v1/user/docs",
        redoc_url="/api/v1/user/redoc",
        openapi_url="/api/v1/user/openapi.json",
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

    app.include_router(health_router)
    app.include_router(api_router)
    register_metrics(app)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
