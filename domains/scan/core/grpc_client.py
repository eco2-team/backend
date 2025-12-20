"""gRPC client for Character domain.

Scan 도메인에서 캐릭터 리워드 평가 시 Character 도메인의 gRPC 서비스를 호출합니다.
Exponential backoff 재시도, Circuit Breaker 및 구조화된 로깅을 지원합니다.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING

import grpc
from aiobreaker import CircuitBreaker, CircuitBreakerError, CircuitBreakerListener

from domains.scan.proto import character_pb2_grpc

if TYPE_CHECKING:
    from domains.scan.core.config import Settings

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


class CircuitBreakerLoggingListener(CircuitBreakerListener):
    """Circuit Breaker 상태 변경 로깅."""

    def state_change(self, breaker: CircuitBreaker, old_state, new_state) -> None:
        logger.warning(
            "Circuit breaker state changed",
            extra={
                "breaker_name": breaker.name,
                "old_state": type(old_state).__name__,
                "new_state": type(new_state).__name__,
                "fail_count": breaker.fail_counter,
            },
        )


class CharacterGrpcClient:
    """gRPC client for CharacterService with retry and circuit breaker support."""

    def __init__(self, settings: "Settings") -> None:
        self.target = settings.character_grpc_target
        self.timeout = settings.grpc_timeout_seconds
        self.max_retries = settings.grpc_max_retries
        self.retry_base_delay = settings.grpc_retry_base_delay
        self.retry_max_delay = settings.grpc_retry_max_delay
        self._channel: grpc.aio.Channel | None = None
        self._stub: character_pb2_grpc.CharacterServiceStub | None = None

        # Circuit Breaker 초기화
        self._circuit_breaker = CircuitBreaker(
            name="character-grpc-client",
            fail_max=settings.grpc_circuit_fail_max,
            timeout_duration=settings.grpc_circuit_timeout_duration,
            listeners=[CircuitBreakerLoggingListener()],
        )

    async def _get_stub(self) -> character_pb2_grpc.CharacterServiceStub:
        """Lazy initialization of gRPC channel and stub."""
        if self._stub is None:
            self._channel = grpc.aio.insecure_channel(self.target)
            self._stub = character_pb2_grpc.CharacterServiceStub(self._channel)
            logger.info(
                "gRPC channel created",
                extra={"target": self.target, "service": "character.CharacterService"},
            )
        return self._stub

    async def _call_with_retry(self, call_func, log_ctx: dict):
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
                        extra={
                            **log_ctx_with_error,
                            "retry_delay_seconds": round(delay, 3),
                        },
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

    async def get_character_reward(self, grpc_request, log_ctx: dict | None = None):
        """
        캐릭터 리워드 평가를 요청합니다.

        Args:
            grpc_request: character_pb2.RewardRequest
            log_ctx: 로깅 컨텍스트

        Returns:
            character_pb2.RewardResponse or None on failure
        """
        log_ctx = log_ctx or {}
        log_ctx["method"] = "GetCharacterReward"

        # Circuit Breaker가 열려 있으면 빠른 실패
        if self._circuit_breaker.current_state.name == "OPEN":
            logger.warning(
                "Circuit breaker is open, failing fast",
                extra={**log_ctx, "circuit_state": "OPEN"},
            )
            return None

        try:
            stub = await self._get_stub()

            async def call_func():
                return await stub.GetCharacterReward(grpc_request, timeout=self.timeout)

            # Circuit Breaker로 감싸서 호출
            response = await self._circuit_breaker.call_async(
                self._call_with_retry, call_func, log_ctx
            )

            logger.info(
                "gRPC call succeeded",
                extra={
                    **log_ctx,
                    "received": response.received,
                    "already_owned": response.already_owned,
                },
            )
            return response

        except CircuitBreakerError:
            logger.warning(
                "Circuit breaker prevented call",
                extra={
                    **log_ctx,
                    "circuit_state": self._circuit_breaker.current_state.name,
                },
            )
            return None
        except grpc.aio.AioRpcError:
            # Already logged in _call_with_retry
            return None
        except Exception:
            # Already logged in _call_with_retry
            return None

    async def close(self) -> None:
        """Close the gRPC channel."""
        if self._channel:
            await self._channel.close()
            logger.debug("gRPC channel closed", extra={"service": "character.CharacterService"})
            self._channel = None
            self._stub = None

    @property
    def circuit_state(self) -> str:
        """현재 Circuit Breaker 상태 반환."""
        return self._circuit_breaker.current_state.name

    @property
    def circuit_fail_count(self) -> int:
        """현재 연속 실패 횟수."""
        return self._circuit_breaker.fail_counter

    def reset_circuit_breaker(self) -> None:
        """Circuit Breaker 상태 리셋 (테스트용)."""
        self._circuit_breaker.close()
        logger.debug("Circuit breaker reset to closed state")


# Singleton instance
_client: CharacterGrpcClient | None = None


def get_character_client() -> CharacterGrpcClient:
    """Get the singleton CharacterGrpcClient instance."""
    global _client
    if _client is None:
        from domains.scan.core.config import get_settings

        _client = CharacterGrpcClient(get_settings())
    return _client


def reset_character_client() -> None:
    """Reset the singleton client (for testing)."""
    global _client
    _client = None


async def close_character_client() -> None:
    """Close the singleton gRPC client channel (for shutdown)."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None


# Legacy compatibility - deprecated
async def get_character_stub() -> character_pb2_grpc.CharacterServiceStub:
    """
    Deprecated: Use get_character_client().get_character_reward() instead.
    Returns stub for backward compatibility.
    """
    client = get_character_client()
    return await client._get_stub()


async def close_channel() -> None:
    """Deprecated: Use close_character_client() instead."""
    await close_character_client()
