"""gRPC client for Character domain.

my 도메인에서 character 도메인의 gRPC 서비스를 호출합니다.
Circuit Breaker 패턴을 적용하여 장애 전파를 방지합니다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

import grpc
from aiobreaker import CircuitBreaker, CircuitBreakerError, CircuitBreakerListener

from domains.my.core.config import Settings, get_settings
from domains.my.proto.character import character_pb2, character_pb2_grpc

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class CircuitBreakerLoggingListener(CircuitBreakerListener):
    """Circuit Breaker 상태 변경 로깅."""

    def state_change(self, breaker: CircuitBreaker, old_state, new_state) -> None:
        logger.warning(
            "Circuit breaker '%s' state changed: %s -> %s",
            breaker.name,
            old_state.name,
            new_state.name,
        )


@dataclass
class DefaultCharacterInfo:
    """기본 캐릭터 정보."""

    character_id: UUID
    character_code: str
    character_name: str
    character_type: str
    character_dialog: str


class CharacterClient:
    """gRPC client for character.CharacterService.

    Circuit Breaker 패턴 적용:
    - fail_max 횟수 실패 시 OPEN 상태로 전환
    - timeout_duration 후 HALF_OPEN 상태에서 재시도
    - 성공 시 CLOSED 상태로 복귀
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._channel: grpc.aio.Channel | None = None
        self._stub: character_pb2_grpc.CharacterServiceStub | None = None

        # Circuit Breaker 설정 주입
        self._circuit_breaker = CircuitBreaker(
            name="character-grpc-client",
            fail_max=self.settings.circuit_fail_max,
            timeout_duration=self.settings.circuit_timeout_duration,
            listeners=[CircuitBreakerLoggingListener()],
        )

    @property
    def _target(self) -> str:
        return f"{self.settings.character_grpc_host}:{self.settings.character_grpc_port}"

    async def _get_stub(self) -> character_pb2_grpc.CharacterServiceStub:
        """Lazy initialization of gRPC channel and stub."""
        if self._stub is None:
            self._channel = grpc.aio.insecure_channel(self._target)
            self._stub = character_pb2_grpc.CharacterServiceStub(self._channel)
            logger.info("Connected to character-api gRPC at %s", self._target)
        return self._stub

    async def get_default_character(self) -> DefaultCharacterInfo | None:
        """기본 캐릭터(이코) 정보를 조회합니다.

        Circuit Breaker가 OPEN 상태이면 즉시 None 반환 (fail-fast).
        gRPC 에러 발생 시에도 None 반환 (graceful degradation).
        """
        try:
            return await self._circuit_breaker.call_async(self._get_default_character_impl)
        except CircuitBreakerError:
            logger.warning(
                "Circuit breaker OPEN - skipping character gRPC call to %s",
                self._target,
            )
            return None
        except grpc.aio.AioRpcError:
            # gRPC 에러는 이미 _get_default_character_impl에서 로깅됨
            # Circuit Breaker가 실패 카운트한 후 예외가 전파됨
            return None
        except Exception:
            # 예상치 못한 에러도 graceful degradation
            return None

    async def _get_default_character_impl(self) -> DefaultCharacterInfo | None:
        """실제 gRPC 호출 구현."""
        try:
            stub = await self._get_stub()
            request = character_pb2.GetDefaultCharacterRequest()
            response = await stub.GetDefaultCharacter(
                request,
                timeout=self.settings.character_grpc_timeout,
            )

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
                "gRPC error calling character.GetDefaultCharacter: %s - %s",
                e.code(),
                e.details(),
            )
            raise  # Circuit Breaker가 실패로 카운트하도록 예외 전파
        except Exception as e:
            logger.exception("Unexpected error calling character.GetDefaultCharacter: %s", e)
            raise

    async def close(self) -> None:
        """Close the gRPC channel."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None
            logger.info("Closed character gRPC channel")


# Singleton instance
_client: CharacterClient | None = None


def get_character_client() -> CharacterClient:
    """Get the singleton CharacterClient instance."""
    global _client
    if _client is None:
        _client = CharacterClient()
    return _client


async def close_character_client() -> None:
    """Close the singleton CharacterClient instance.

    FastAPI lifespan에서 호출하여 리소스를 정리합니다.
    """
    global _client
    if _client is not None:
        await _client.close()
        _client = None
