from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from domains.chat.api.v1.routers import api_router, health_router
from domains.chat.core.constants import SERVICE_VERSION
from domains.chat.core.logging import configure_logging
from domains.chat.metrics import register_metrics

# 구조화된 로깅 설정 (ECS JSON 포맷)
configure_logging()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Chat API",
        description="Conversational assistant for recycling topics",
        version=SERVICE_VERSION,
        docs_url="/api/v1/chat/docs",
        openapi_url="/api/v1/chat/openapi.json",
        redoc_url=None,
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
    app.include_router(api_router, prefix="/api/v1")
    register_metrics(app)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
