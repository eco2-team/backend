"""gRPC client for Character domain.

my 도메인에서 character 도메인의 gRPC 서비스를 호출합니다.
"""

import logging
import os
from dataclasses import dataclass
from uuid import UUID

import grpc

from domains.my.proto.character import character_pb2, character_pb2_grpc

logger = logging.getLogger(__name__)

# character-api gRPC 서버 주소 (Kubernetes 서비스 이름)
CHARACTER_GRPC_HOST = os.getenv("CHARACTER_GRPC_HOST", "character-api.character.svc.cluster.local")
CHARACTER_GRPC_PORT = os.getenv("CHARACTER_GRPC_PORT", "50051")


@dataclass
class DefaultCharacterInfo:
    """기본 캐릭터 정보."""

    character_id: UUID
    character_code: str
    character_name: str
    character_type: str
    character_dialog: str


class CharacterClient:
    """gRPC client for character.CharacterService."""

    def __init__(self, host: str | None = None, port: str | None = None):
        self.host = host or CHARACTER_GRPC_HOST
        self.port = port or CHARACTER_GRPC_PORT
        self._channel: grpc.aio.Channel | None = None
        self._stub: character_pb2_grpc.CharacterServiceStub | None = None

    async def _get_stub(self) -> character_pb2_grpc.CharacterServiceStub:
        """Lazy initialization of gRPC channel and stub."""
        if self._stub is None:
            target = f"{self.host}:{self.port}"
            self._channel = grpc.aio.insecure_channel(target)
            self._stub = character_pb2_grpc.CharacterServiceStub(self._channel)
            logger.info(f"Connected to character-api gRPC at {target}")
        return self._stub

    async def get_default_character(self) -> DefaultCharacterInfo | None:
        """기본 캐릭터(이코) 정보를 조회합니다."""
        try:
            stub = await self._get_stub()
            request = character_pb2.GetDefaultCharacterRequest()
            response = await stub.GetDefaultCharacter(request, timeout=5.0)

            if not response.found:
                logger.warning("Default character not found")
                return None

            logger.info("Got default character: %s", response.character_name)
            return DefaultCharacterInfo(
                character_id=UUID(response.character_id),
                character_code=response.character_code,
                character_name=response.character_name,
                character_type=response.character_type,
                character_dialog=response.character_dialog,
            )
        except grpc.aio.AioRpcError as e:
            logger.error(
                f"gRPC error calling character.GetDefaultCharacter: {e.code()} - {e.details()}"
            )
            return None
        except Exception as e:
            logger.exception(f"Unexpected error calling character.GetDefaultCharacter: {e}")
            return None

    async def close(self):
        """Close the gRPC channel."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None


# Singleton instance
_client: CharacterClient | None = None


def get_character_client() -> CharacterClient:
    """Get the singleton CharacterClient instance."""
    global _client
    if _client is None:
        _client = CharacterClient()
    return _client
