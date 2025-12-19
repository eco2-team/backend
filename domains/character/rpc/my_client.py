"""gRPC client for My (User Profile) domain.

character 도메인에서 캐릭터 지급 시 my 도메인의 gRPC 서비스를 호출합니다.
Exponential backoff 재시도 및 구조화된 로깅을 지원합니다.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING
from uuid import UUID

import grpc

from domains.character.proto.my import user_character_pb2, user_character_pb2_grpc

if TYPE_CHECKING:
    from domains.character.core.config import Settings

logger = logging.getLogger(__name__)

# 재시도 가능한 gRPC 상태 코드
RETRYABLE_STATUS_CODES = frozenset(
    {
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.DEADLINE_EXCEEDED,
        grpc.StatusCode.RESOURCE_EXHAUSTED,
        grpc.StatusCode.ABORTED,
    }
)


class MyUserCharacterClient:
    """gRPC client for my.UserCharacterService with retry support."""

    def __init__(self, settings: Settings) -> None:
        self.host = settings.my_grpc_host
        self.port = settings.my_grpc_port
        self.timeout = settings.grpc_timeout_seconds
        self.max_retries = settings.grpc_max_retries
        self.retry_base_delay = settings.grpc_retry_base_delay
        self.retry_max_delay = settings.grpc_retry_max_delay
        self._channel: grpc.aio.Channel | None = None
        self._stub: user_character_pb2_grpc.UserCharacterServiceStub | None = None

    async def _get_stub(self) -> user_character_pb2_grpc.UserCharacterServiceStub:
        """Lazy initialization of gRPC channel and stub."""
        if self._stub is None:
            target = f"{self.host}:{self.port}"
            self._channel = grpc.aio.insecure_channel(target)
            self._stub = user_character_pb2_grpc.UserCharacterServiceStub(self._channel)
            logger.info(
                "gRPC channel created",
                extra={"target": target, "service": "my.UserCharacterService"},
            )
        return self._stub

    async def _call_with_retry(
        self,
        call_func,
        log_ctx: dict,
    ):
        """Execute gRPC call with exponential backoff retry."""
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return await call_func()

            except grpc.aio.AioRpcError as e:
                last_error = e
                status_code = e.code()

                log_ctx_with_error = {
                    **log_ctx,
                    "attempt": attempt + 1,
                    "max_retries": self.max_retries,
                    "grpc_code": status_code.name,
                    "grpc_details": e.details(),
                }

                if status_code in RETRYABLE_STATUS_CODES and attempt < self.max_retries:
                    # Calculate delay with exponential backoff + jitter
                    delay = min(
                        self.retry_base_delay * (2**attempt),
                        self.retry_max_delay,
                    )
                    # Add jitter (±25%)
                    delay = delay * (0.75 + random.random() * 0.5)

                    logger.warning(
                        "gRPC call failed, retrying",
                        extra={**log_ctx_with_error, "retry_delay_seconds": round(delay, 3)},
                    )
                    await asyncio.sleep(delay)
                else:
                    # Non-retryable error or max retries exceeded
                    logger.error(
                        "gRPC call failed permanently",
                        extra=log_ctx_with_error,
                    )
                    raise

            except Exception as e:
                # Unexpected error - don't retry
                logger.exception(
                    "Unexpected error in gRPC call",
                    extra={**log_ctx, "error": str(e)},
                )
                raise

        # Should not reach here, but just in case
        if last_error:
            raise last_error

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
        log_ctx = {
            "method": "GrantCharacter",
            "user_id": str(user_id),
            "character_id": str(character_id),
            "character_name": character_name,
            "source": source,
        }

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

            async def call_func():
                return await stub.GrantCharacter(request, timeout=self.timeout)

            response = await self._call_with_retry(call_func, log_ctx)

            logger.info(
                "gRPC call succeeded",
                extra={
                    **log_ctx,
                    "success": response.success,
                    "already_owned": response.already_owned,
                },
            )
            return response.success, response.already_owned

        except grpc.aio.AioRpcError:
            # Already logged in _call_with_retry
            return False, False
        except Exception:
            # Already logged in _call_with_retry
            return False, False

    async def close(self) -> None:
        """Close the gRPC channel."""
        if self._channel:
            await self._channel.close()
            logger.debug("gRPC channel closed", extra={"service": "my.UserCharacterService"})
            self._channel = None
            self._stub = None


# Singleton instance
_client: MyUserCharacterClient | None = None


def get_my_client() -> MyUserCharacterClient:
    """Get the singleton MyUserCharacterClient instance."""
    global _client
    if _client is None:
        from domains.character.core.config import get_settings

        _client = MyUserCharacterClient(get_settings())
    return _client


def reset_my_client() -> None:
    """Reset the singleton client (for testing)."""
    global _client
    _client = None


async def close_my_client() -> None:
    """Close the singleton gRPC client channel (for shutdown)."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
