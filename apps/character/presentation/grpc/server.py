"""gRPC Server for Character Service.

Clean Architecture 기반 gRPC 서버 진입점입니다.
Graceful shutdown, OpenTelemetry 트레이싱을 지원합니다.

Usage:
    python -m apps.character.presentation.grpc.server
"""

from __future__ import annotations

import asyncio
import logging
import signal
from concurrent import futures

import grpc

from character.application.reward import EvaluateRewardCommand
from character.infrastructure.persistence_postgres import (
    SqlaCharacterReader,
    SqlaOwnershipChecker,
)
from character.presentation.grpc.servicers import CharacterServicer
from character.proto import character_pb2_grpc
from character.setup.config import get_settings
from character.setup.database import async_session_factory

logger = logging.getLogger(__name__)


class GrpcDependencyFactory:
    """gRPC Servicer 의존성 팩토리.

    각 요청마다 새로운 DB 세션을 생성하고,
    요청 종료 시 정리합니다.
    """

    def __init__(self) -> None:
        """Initialize."""
        self._session_factory = async_session_factory

    async def create_servicer(self) -> CharacterServicer:
        """Servicer 인스턴스를 생성합니다.

        Note:
            gRPC는 단일 Servicer 인스턴스를 재사용하므로,
            Servicer 내부에서 per-request 세션 관리가 필요합니다.
        """
        # 서버 시작 시 한 번만 생성되는 세션 (Servicer 생명주기)
        # 실제로는 Servicer 내부에서 per-request 세션 관리 권장
        async with self._session_factory() as session:
            character_reader = SqlaCharacterReader(session)
            ownership_checker = SqlaOwnershipChecker(session)

            evaluate_command = EvaluateRewardCommand(
                matcher=character_reader,
                ownership_checker=ownership_checker,
            )

            return CharacterServicer(
                evaluate_command=evaluate_command,
                character_matcher=character_reader,
            )


class SessionAwareCharacterServicer(character_pb2_grpc.CharacterServiceServicer):
    """Per-request DB 세션을 관리하는 Servicer 래퍼.

    각 gRPC 호출마다 새로운 DB 세션을 생성하고,
    호출 완료 후 세션을 정리합니다.
    """

    def __init__(self) -> None:
        """Initialize."""
        self._session_factory = async_session_factory

    async def _create_inner_servicer(self) -> CharacterServicer:
        """요청별 Servicer를 생성합니다."""
        session = self._session_factory()
        async with session:
            character_reader = SqlaCharacterReader(session)
            ownership_checker = SqlaOwnershipChecker(session)

            evaluate_command = EvaluateRewardCommand(
                matcher=character_reader,
                ownership_checker=ownership_checker,
            )

            return CharacterServicer(
                evaluate_command=evaluate_command,
                character_matcher=character_reader,
            )

    async def GetCharacterReward(
        self,
        request: character_pb2_grpc.character__pb2.RewardRequest,
        context: grpc.aio.ServicerContext,
    ) -> character_pb2_grpc.character__pb2.RewardResponse:
        """캐릭터 리워드를 평가합니다."""
        async with self._session_factory() as session:
            character_reader = SqlaCharacterReader(session)
            ownership_checker = SqlaOwnershipChecker(session)

            evaluate_command = EvaluateRewardCommand(
                matcher=character_reader,
                ownership_checker=ownership_checker,
            )

            servicer = CharacterServicer(
                evaluate_command=evaluate_command,
                character_matcher=character_reader,
            )

            return await servicer.GetCharacterReward(request, context)

    async def GetDefaultCharacter(
        self,
        request: character_pb2_grpc.character__pb2.GetDefaultCharacterRequest,
        context: grpc.aio.ServicerContext,
    ) -> character_pb2_grpc.character__pb2.GetDefaultCharacterResponse:
        """기본 캐릭터 정보를 조회합니다."""
        async with self._session_factory() as session:
            character_reader = SqlaCharacterReader(session)
            ownership_checker = SqlaOwnershipChecker(session)

            evaluate_command = EvaluateRewardCommand(
                matcher=character_reader,
                ownership_checker=ownership_checker,
            )

            servicer = CharacterServicer(
                evaluate_command=evaluate_command,
                character_matcher=character_reader,
            )

            return await servicer.GetDefaultCharacter(request, context)


async def serve() -> None:
    """gRPC 서버를 시작합니다."""
    settings = get_settings()

    # OpenTelemetry 설정 (선택적)
    if settings.otel_enabled:
        try:
            from character.infrastructure.observability import setup_tracing

            setup_tracing(f"{settings.service_name}-grpc")
            logger.info("OpenTelemetry tracing enabled for gRPC server")
        except ImportError:
            logger.warning("OpenTelemetry not available, skipping tracing setup")

    # gRPC 서버 생성
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ("grpc.max_send_message_length", 50 * 1024 * 1024),
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),
        ],
    )

    # Servicer 등록 (per-request 세션 관리)
    servicer = SessionAwareCharacterServicer()
    character_pb2_grpc.add_CharacterServiceServicer_to_server(servicer, server)

    # 서버 시작
    listen_addr = f"[::]:{settings.grpc_port}"
    server.add_insecure_port(listen_addr)

    logger.info(
        "Starting gRPC server",
        extra={
            "address": listen_addr,
            "environment": settings.environment,
        },
    )

    await server.start()

    # Graceful shutdown 설정
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
    logger.info("gRPC server stopped")


def configure_logging() -> None:
    """로깅을 설정합니다."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


if __name__ == "__main__":
    configure_logging()
    asyncio.run(serve())
