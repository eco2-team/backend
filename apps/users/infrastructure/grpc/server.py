"""gRPC server for Users service.

auth 도메인에서 호출하는 사용자 관련 gRPC 서비스입니다.

Usage:
    python -m apps.users.infrastructure.grpc.server
"""

from __future__ import annotations

import asyncio
import logging
import signal
from concurrent import futures

import grpc

from apps.users.infrastructure.grpc import users_pb2_grpc
from apps.users.infrastructure.grpc.servicers import UsersServicer
from apps.users.infrastructure.persistence_postgres.mappings.auth_user import (
    start_auth_mappers,
)
from apps.users.infrastructure.persistence_postgres.session import (
    async_session_factory,
)
from apps.users.setup.config import get_settings
from apps.users.setup.logging import setup_logging

logger = logging.getLogger(__name__)


async def serve() -> None:
    """Start the gRPC server with graceful shutdown support."""
    settings = get_settings()

    # 로깅 설정
    setup_logging()

    # ORM 매퍼 초기화
    start_auth_mappers()

    # gRPC 서버 생성
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=settings.grpc_max_workers),
    )

    # Servicer 등록
    users_pb2_grpc.add_UsersServiceServicer_to_server(
        UsersServicer(session_factory=async_session_factory),
        server,
    )

    # 포트 바인딩
    listen_addr = f"[::]:{settings.grpc_server_port}"
    server.add_insecure_port(listen_addr)

    logger.info(
        "Starting Users gRPC server",
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

    logger.info("Users gRPC server started, waiting for requests")
    await stop_event.wait()

    logger.info("Stopping gRPC server gracefully")
    await server.stop(grace=5)
    logger.info("Users gRPC server stopped")


if __name__ == "__main__":
    asyncio.run(serve())
