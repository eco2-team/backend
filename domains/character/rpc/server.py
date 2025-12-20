"""gRPC server for Character service.

설정 기반 구성, 분산 트레이싱, 구조화된 로깅을 지원합니다.

Observability:
    - OpenTelemetry gRPC Server instrumentation
    - Jaeger에서 인바운드 RPC 호출 추적 가능
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from concurrent import futures

import grpc

from domains.character.core.config import get_settings
from domains.character.core.constants import (
    DEFAULT_ENVIRONMENT,
    ENV_KEY_ENVIRONMENT,
    SERVICE_NAME,
    SERVICE_VERSION,
)
from domains.character.core.logging import configure_logging
from domains.character.core.tracing import (
    configure_tracing,
    instrument_grpc_server,
    shutdown_tracing,
)
from domains.character.proto import character_pb2_grpc
from domains.character.rpc.v1.character_servicer import CharacterServicer

logger = logging.getLogger(__name__)


async def serve() -> None:
    """Start the gRPC server with graceful shutdown support."""
    settings = get_settings()

    # OpenTelemetry 분산 트레이싱 설정 (gRPC 서버용)
    environment = os.getenv(ENV_KEY_ENVIRONMENT, DEFAULT_ENVIRONMENT)
    configure_tracing(
        service_name=f"{SERVICE_NAME}-grpc",
        service_version=SERVICE_VERSION,
        environment=environment,
    )

    # gRPC 서버 instrumentation (인바운드 요청 추적)
    instrument_grpc_server(None)  # 전역 instrumentation

    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=settings.grpc_max_workers))
    character_pb2_grpc.add_CharacterServiceServicer_to_server(CharacterServicer(), server)

    listen_addr = f"[::]:{settings.grpc_server_port}"
    server.add_insecure_port(listen_addr)

    logger.info(
        "Starting gRPC server",
        extra={
            "address": listen_addr,
            "max_workers": settings.grpc_max_workers,
            "environment": settings.environment,
        },
    )

    await server.start()

    # Graceful shutdown handler
    stop_event = asyncio.Event()

    def handle_signal(sig: signal.Signals) -> None:
        logger.info("Received shutdown signal", extra={"signal": sig.name})
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal, sig)

    logger.info("gRPC server started, waiting for requests")
    await stop_event.wait()

    logger.info("Stopping gRPC server gracefully")
    await server.stop(grace=5)

    # Graceful tracing shutdown
    shutdown_tracing()
    logger.info("gRPC server stopped")


if __name__ == "__main__":
    # Configure structured logging for standalone execution
    configure_logging()
    asyncio.run(serve())
