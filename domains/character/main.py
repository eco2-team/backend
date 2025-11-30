from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from domains.character.api.v1.routers import api_router, health_router, metrics_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Character API",
        description="Character analysis and storytelling service",
        version="0.7.3",
        docs_url="/api/v1/character/docs",
        openapi_url="/api/v1/character/openapi.json",
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
    app.include_router(metrics_router)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


__all__ = ["app", "create_app"]
