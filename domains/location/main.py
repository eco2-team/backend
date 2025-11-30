from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from domains.location.app.api.v1.routers import api_router, health_router
except ModuleNotFoundError:  # pragma: no cover
    # 로컬 부트스트랩 환경에서 uvicorn main:app 형태로 실행하면
    # PYTHONPATH에 프로젝트 루트가 잡히지 않아 domains.* import가 실패하므로 보정한다.
    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))

    from domains.location.app.api.v1.routers import api_router, health_router


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
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
