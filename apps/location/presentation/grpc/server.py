"""gRPC Server for Location Service.

Clean Architecture 기반 gRPC 서버 진입점입니다.

Usage:
    # HTTP와 별도로 실행
    python -m location.presentation.grpc.server

    # 또는 main.py에서 병행 실행
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import grpc

from location.presentation.grpc.servicers import LocationServicer
from location.proto import location_pb2_grpc
from location.setup.config import get_settings
from location.setup.dependencies import get_nearby_centers_query

if TYPE_CHECKING:
    from location.application.nearby import GetNearbyCentersQuery

logger = logging.getLogger(__name__)


async def create_servicer() -> LocationServicer:
    """Servicer 생성 (의존성 주입)."""
    query = await get_nearby_centers_query()
    return LocationServicer(nearby_query=query)


async def serve() -> None:
    """gRPC 서버를 시작합니다."""
    settings = get_settings()

    # Servicer 생성
    servicer = await create_servicer()

    # gRPC 서버 생성
    server = grpc.aio.server(
        options=[
            ("grpc.max_send_message_length", 50 * 1024 * 1024),
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),
        ]
    )

    # Servicer 등록
    location_pb2_grpc.add_LocationServiceServicer_to_server(servicer, server)

    # 포트 바인딩
    listen_addr = f"[::]:{settings.grpc_port}"
    server.add_insecure_port(listen_addr)

    logger.info(
        "Starting Location gRPC server",
        extra={"address": listen_addr},
    )

    await server.start()

    logger.info("Location gRPC server started, waiting for requests")

    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        logger.info("Stopping Location gRPC server gracefully")
        await server.stop(5)
        logger.info("Location gRPC server stopped")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(serve())
