"""gRPC client for My (User Profile) domain.

character 도메인에서 캐릭터 지급 시 my 도메인의 gRPC 서비스를 호출합니다.
"""

import logging
import os
from uuid import UUID

import grpc

from domains.character.proto.my import user_character_pb2, user_character_pb2_grpc

logger = logging.getLogger(__name__)

# my-api gRPC 서버 주소 (Kubernetes 서비스 이름)
MY_GRPC_HOST = os.getenv("MY_GRPC_HOST", "my-api.my.svc.cluster.local")
MY_GRPC_PORT = os.getenv("MY_GRPC_PORT", "50052")


class MyUserCharacterClient:
    """gRPC client for my.UserCharacterService."""

    def __init__(self, host: str | None = None, port: str | None = None):
        self.host = host or MY_GRPC_HOST
        self.port = port or MY_GRPC_PORT
        self._channel: grpc.aio.Channel | None = None
        self._stub: user_character_pb2_grpc.UserCharacterServiceStub | None = None

    async def _get_stub(self) -> user_character_pb2_grpc.UserCharacterServiceStub:
        """Lazy initialization of gRPC channel and stub."""
        if self._stub is None:
            target = f"{self.host}:{self.port}"
            self._channel = grpc.aio.insecure_channel(target)
            self._stub = user_character_pb2_grpc.UserCharacterServiceStub(self._channel)
            logger.info(f"Connected to my-api gRPC at {target}")
        return self._stub

    async def grant_character(
        self,
        user_id: UUID,
        character_id: UUID,
        character_code: str,
        character_name: str,
        character_type: str | None,
        character_dialog: str | None,
        source: str,
    ) -> tuple[bool, bool]:
        """
        캐릭터를 사용자에게 지급합니다.

        Returns:
            tuple[bool, bool]: (success, already_owned)
        """
        try:
            stub = await self._get_stub()
            request = user_character_pb2.GrantCharacterRequest(
                user_id=str(user_id),
                character_id=str(character_id),
                character_code=character_code,
                character_name=character_name,
                character_type=character_type or "",
                character_dialog=character_dialog or "",
                source=source,
            )
            response = await stub.GrantCharacter(request, timeout=5.0)
            logger.info(
                "GrantCharacter response: success=%s, already_owned=%s, message=%s",
                response.success,
                response.already_owned,
                response.message,
            )
            return response.success, response.already_owned
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error calling my.GrantCharacter: {e.code()} - {e.details()}")
            # gRPC 호출 실패 시에도 기존 로직은 계속 진행 (fallback)
            return False, False
        except Exception as e:
            logger.exception(f"Unexpected error calling my.GrantCharacter: {e}")
            return False, False

    async def close(self):
        """Close the gRPC channel."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None


# Singleton instance
_client: MyUserCharacterClient | None = None


def get_my_client() -> MyUserCharacterClient:
    """Get the singleton MyUserCharacterClient instance."""
    global _client
    if _client is None:
        _client = MyUserCharacterClient()
    return _client
