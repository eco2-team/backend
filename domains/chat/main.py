import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from domains.chat.api.v1.routers import api_router, health_router
from domains.chat.metrics import register_metrics


def create_app() -> FastAPI:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    app = FastAPI(
        title="Chat API",
        description="Conversational assistant for recycling topics",
        version="0.7.3",
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
