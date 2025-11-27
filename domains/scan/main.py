from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from domains.scan.api.v1.endpoints import api_router, health_router


def create_app() -> FastAPI:
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
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(api_router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
