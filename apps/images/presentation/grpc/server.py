"""gRPC Server for Image Service.

내부 서비스에서 이미지 업로드를 처리하는 gRPC 서버입니다.
메인 FastAPI 앱과 별도로 실행됩니다.

Usage:
    python -m images.presentation.grpc.server
"""

from __future__ import annotations

import asyncio
import logging
import signal
from concurrent import futures

import boto3
import grpc

from images.core import get_settings
from images.presentation.grpc.servicers import ImageServicer
from images.proto import image_pb2_grpc

logger = logging.getLogger(__name__)


async def serve(standalone: bool = False) -> None:
    """gRPC 서버를 시작합니다.

    Args:
        standalone: True면 시그널 핸들러 등록 (독립 실행 시)
                   False면 wait_for_termination만 사용 (FastAPI 임베디드 시)
    """
    settings = get_settings()

    # S3 클라이언트 생성
    s3_client = boto3.client(
        "s3",
        region_name=settings.aws_region,
    )

    # gRPC 서버 생성
    # 이미지 데이터를 위해 max message size 증가 (10MB)
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ("grpc.max_send_message_length", 10 * 1024 * 1024),
            ("grpc.max_receive_message_length", 10 * 1024 * 1024),
        ],
    )

    # Servicer 등록
    servicer = ImageServicer(
        s3_client=s3_client,
        settings=settings,
    )
    image_pb2_grpc.add_ImageServiceServicer_to_server(servicer, server)

    # 서버 시작
    grpc_port = getattr(settings, "grpc_port", 50052)
    listen_addr = f"[::]:{grpc_port}"
    server.add_insecure_port(listen_addr)

    logger.info(
        "Starting gRPC server",
        extra={
            "address": listen_addr,
            "s3_bucket": settings.s3_bucket,
            "cdn_domain": str(settings.cdn_domain),
        },
    )

    await server.start()
    logger.info("gRPC server started, waiting for requests")

    if standalone:
        # 독립 실행 시: 시그널 핸들러로 종료 대기
        stop_event = asyncio.Event()

        def handle_signal(sig: signal.Signals) -> None:
            logger.info("Received shutdown signal", extra={"signal": sig.name})
            stop_event.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, handle_signal, sig)

        await stop_event.wait()
    else:
        # FastAPI 임베디드 시: 취소될 때까지 대기
        try:
            await server.wait_for_termination()
        except asyncio.CancelledError:
            pass

    logger.info("Stopping gRPC server gracefully")
    await server.stop(grace=5)
    logger.info("gRPC server stopped")


def configure_logging() -> None:
    """로깅을 설정합니다."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


if __name__ == "__main__":
    configure_logging()
    asyncio.run(serve(standalone=True))
