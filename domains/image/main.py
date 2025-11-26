from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from domains.image.api.v1.routers import api_router, health_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Image API",
        description="Eco image ingestion and delivery service",
        version="0.7.3",
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
