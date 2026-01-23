import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from images.api.errors import register_exception_handlers
from images.api.v1.routers import api_router, health_router
from images.core.constants import (
    DEFAULT_ENVIRONMENT,
    ENV_KEY_ENVIRONMENT,
    SERVICE_NAME,
    SERVICE_VERSION,
)
from images.core.logging import configure_logging
from images.core.tracing import (
    configure_tracing,
    instrument_fastapi,
    instrument_httpx,
    shutdown_tracing,
)
from images.metrics import register_metrics
from images.presentation.grpc.server import serve as serve_grpc

logger = logging.getLogger(__name__)

# 구조화된 로깅 설정 (ECS JSON 포맷)
configure_logging()

# OpenTelemetry 분산 트레이싱 설정
environment = os.getenv(ENV_KEY_ENVIRONMENT, DEFAULT_ENVIRONMENT)
configure_tracing(
    service_name=SERVICE_NAME,
    service_version=SERVICE_VERSION,
    environment=environment,
)

# 글로벌 instrumentation
instrument_httpx()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # gRPC 서버를 백그라운드에서 시작
    grpc_task = asyncio.create_task(serve_grpc())

    # 시작 직후 짧은 대기로 초기화 에러 확인
    await asyncio.sleep(0.1)
    if grpc_task.done():
        exc = grpc_task.exception()
        if exc:
            logger.error("gRPC server failed to start", exc_info=exc)
            raise exc

    logger.info("gRPC server started in background")

    yield

    # gRPC 서버 종료
    grpc_task.cancel()
    try:
        await grpc_task
    except asyncio.CancelledError:
        logger.info("gRPC server stopped")
    shutdown_tracing()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Image API",
        description="Eco image ingestion and delivery service",
        version=SERVICE_VERSION,
        docs_url="/api/v1/images/docs",
        openapi_url="/api/v1/images/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
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

    # OpenTelemetry FastAPI instrumentation
    instrument_fastapi(app)

    # 예외 핸들러 등록
    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(api_router)
    register_metrics(app)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
