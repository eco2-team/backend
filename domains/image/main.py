from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from domains.image.api.v1.routers import api_router, health_router
from domains.image.core.constants import SERVICE_VERSION
from domains.image.core.logging import configure_logging
from domains.image.metrics import register_metrics

# 구조화된 로깅 설정 (ECS JSON 포맷)
configure_logging()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Image API",
        description="Eco image ingestion and delivery service",
        version=SERVICE_VERSION,
        docs_url="/api/v1/images/docs",
        openapi_url="/api/v1/images/openapi.json",
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
    app.include_router(api_router)
    register_metrics(app)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
