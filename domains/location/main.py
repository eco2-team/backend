from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from domains.location.api.v1.routers import api_router, health_router
from domains.location.metrics import register_metrics


def create_app() -> FastAPI:
    app = FastAPI(
        title="Location API",
        description="Geospatial lookup for recycling facilities",
        version="0.7.3",
        docs_url="/api/v1/locations/docs",
        redoc_url="/api/v1/locations/redoc",
        openapi_url="/api/v1/locations/openapi.json",
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
