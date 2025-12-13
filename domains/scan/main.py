import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from domains.scan.api.v1.endpoints import api_router, health_router
from domains.scan.metrics import register_metrics


def create_app() -> FastAPI:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    app = FastAPI(
        title="Scan API",
        description="Waste classification pipeline",
        version="0.7.3",
        docs_url="/api/v1/scan/docs",
        openapi_url="/api/v1/scan/openapi.json",
        redoc_url="/api/v1/scan/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://frontend1.dev.growbin.app",
            "https://frontend2.dev.growbin.app",
            "https://frontend.dev.growbin.app",
            "http://localhost:5173",
            "https://localhost:5173",
            "http://127.0.0.1:5173",
            "https://127.0.0.1:5173",
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
