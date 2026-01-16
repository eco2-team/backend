"""Character gRPC Client - CharacterClientPort 구현체.

Character API의 gRPC 서비스를 호출하는 클라이언트.

왜 gRPC인가? (Direct Call vs Queue-based)
- LangGraph는 asyncio 기반 오케스트레이션
- gRPC는 grpc.aio로 asyncio 네이티브 지원
- Celery Worker는 Fire & Forget에 적합, 결과 대기에 부적합
- Character API의 LocalCache는 즉시 응답 (~1-3ms)

Clean Architecture:
- Port: CharacterClientPort (application/integrations/character/ports)
- Adapter: CharacterGrpcClient (이 파일)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import grpc

from chat_worker.application.ports.character_client import (
    CharacterClientPort,
    CharacterDTO,
)
from chat_worker.infrastructure.integrations.character.proto import (
    character_pb2,
    character_pb2_grpc,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# gRPC 타임아웃 (초) - 서비스 SLA 기반
# Character API는 LocalCache로 ~1-3ms 응답, 3초면 충분
DEFAULT_GRPC_TIMEOUT = 3.0


class CharacterGrpcClient(CharacterClientPort):
    """Character gRPC 클라이언트.

    순수 API 호출만 담당합니다.
    비즈니스 로직은 CharacterService에서 수행.

    사용 예:
        client = CharacterGrpcClient()
        char = await client.get_character_by_waste_category("플라스틱")
        if char:
            context = CharacterService.to_answer_context(char)
    """

    def __init__(
        self,
        host: str = "character-api",
        port: int = 50051,
    ):
        """Initialize.

        Args:
            host: Character API gRPC host
            port: Character API gRPC port
        """
        self._address = f"{host}:{port}"
        self._channel: grpc.aio.Channel | None = None
        self._stub: character_pb2_grpc.CharacterServiceStub | None = None

    async def _get_stub(self) -> character_pb2_grpc.CharacterServiceStub:
        """Lazy connection - 첫 호출 시 연결."""
        if self._channel is None:
            self._channel = grpc.aio.insecure_channel(self._address)
            self._stub = character_pb2_grpc.CharacterServiceStub(self._channel)
            logger.info(
                "Character gRPC channel created",
                extra={"address": self._address},
            )
        return self._stub

    async def get_character_by_waste_category(
        self,
        waste_category: str,
    ) -> CharacterDTO | None:
        """폐기물 카테고리로 캐릭터 조회.

        gRPC로 Character API의 GetCharacterByMatch 호출.

        Args:
            waste_category: 폐기물 중분류 (예: "플라스틱", "종이류")

        Returns:
            매칭된 캐릭터 정보 또는 None
        """
        stub = await self._get_stub()

        request = character_pb2.GetByMatchRequest(match_label=waste_category)

        try:
            response = await stub.GetCharacterByMatch(
                request, timeout=DEFAULT_GRPC_TIMEOUT
            )

            if not response.found:
                logger.info(
                    "Character not found via gRPC",
                    extra={"waste_category": waste_category},
                )
                return None

            logger.info(
                "Character found via gRPC",
                extra={
                    "waste_category": waste_category,
                    "character_name": response.character_name,
                },
            )

            return CharacterDTO(
                name=response.character_name,
                type_label=response.character_type,
                dialog=response.character_dialog,
                match_label=response.match_label,
            )

        except grpc.aio.AioRpcError as e:
            logger.error(
                "Character gRPC error",
                extra={
                    "waste_category": waste_category,
                    "code": e.code().name,
                    "details": e.details(),
                },
            )
            return None

    async def get_catalog(self) -> list[CharacterDTO]:
        """전체 카탈로그 조회.

        Note: gRPC에는 해당 RPC가 없으므로 빈 리스트 반환.
        전체 조회가 필요하면 HTTP API 사용 권장.
        """
        logger.warning("get_catalog not implemented in gRPC client")
        return []

    async def close(self) -> None:
        """연결 종료."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None
            logger.info("Character gRPC channel closed")
