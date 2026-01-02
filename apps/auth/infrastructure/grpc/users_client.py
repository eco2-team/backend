"""gRPC client for Users service.

auth 도메인에서 users 도메인의 사용자 관련 기능을 호출합니다.
Circuit Breaker, Retry 및 구조화된 로깅을 지원합니다.

참고: https://rooftopsnow.tistory.com/127
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING

import grpc
from aiobreaker import CircuitBreaker, CircuitBreakerError, CircuitBreakerListener

from apps.auth.infrastructure.grpc import users_pb2, users_pb2_grpc

if TYPE_CHECKING:
    from apps.auth.setup.config import Settings

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


class UsersGrpcClient:
    """gRPC client for UsersService with retry and circuit breaker support."""

    def __init__(self, settings: "Settings") -> None:
        self.target = settings.users_grpc_target
        self.timeout = settings.grpc_timeout_seconds
        self.max_retries = settings.grpc_max_retries
        self.retry_base_delay = settings.grpc_retry_base_delay
        self.retry_max_delay = settings.grpc_retry_max_delay
        self._channel: grpc.aio.Channel | None = None
        self._stub: users_pb2_grpc.UsersServiceStub | None = None

        # Circuit Breaker 초기화
        self._circuit_breaker = CircuitBreaker(
            name="users-grpc-client",
            fail_max=settings.grpc_circuit_fail_max,
            timeout_duration=settings.grpc_circuit_timeout_duration,
            listeners=[CircuitBreakerLoggingListener()],
        )

    async def _get_stub(self) -> users_pb2_grpc.UsersServiceStub:
        """Lazy initialization of gRPC channel and stub."""
        if self._stub is None:
            self._channel = grpc.aio.insecure_channel(self.target)
            self._stub = users_pb2_grpc.UsersServiceStub(self._channel)
            logger.info(
                "gRPC channel created",
                extra={"target": self.target, "service": "users.UsersService"},
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

    async def get_or_create_from_oauth(
        self,
        *,
        provider: str,
        provider_user_id: str,
        email: str | None = None,
        nickname: str | None = None,
        profile_image_url: str | None = None,
    ) -> users_pb2.GetOrCreateFromOAuthResponse | None:
        """OAuth 프로필로 사용자 조회 또는 생성.

        Args:
            provider: OAuth 프로바이더 (google, kakao, naver)
            provider_user_id: 프로바이더에서의 사용자 ID
            email: 이메일 (선택)
            nickname: 닉네임 (선택)
            profile_image_url: 프로필 이미지 URL (선택)

        Returns:
            GetOrCreateFromOAuthResponse or None on failure
        """
        log_ctx = {
            "method": "GetOrCreateFromOAuth",
            "provider": provider,
        }

        # Circuit Breaker가 열려 있으면 빠른 실패
        if self._circuit_breaker.current_state.name == "OPEN":
            logger.warning(
                "Circuit breaker is open, failing fast",
                extra={**log_ctx, "circuit_state": "OPEN"},
            )
            return None

        try:
            stub = await self._get_stub()

            request = users_pb2.GetOrCreateFromOAuthRequest(
                provider=provider,
                provider_user_id=provider_user_id,
            )
            if email:
                request.email = email
            if nickname:
                request.nickname = nickname
            if profile_image_url:
                request.profile_image_url = profile_image_url

            async def call_func():
                return await stub.GetOrCreateFromOAuth(request, timeout=self.timeout)

            # Circuit Breaker로 감싸서 호출
            response = await self._circuit_breaker.call_async(
                self._call_with_retry, call_func, log_ctx
            )

            logger.info(
                "gRPC GetOrCreateFromOAuth succeeded",
                extra={
                    **log_ctx,
                    "user_id": response.user.id,
                    "is_new_user": response.is_new_user,
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

    async def update_login_time(
        self,
        *,
        user_id: str,
        provider: str,
        provider_user_id: str,
    ) -> bool:
        """로그인 시간 업데이트.

        Args:
            user_id: 사용자 ID
            provider: OAuth 프로바이더
            provider_user_id: 프로바이더에서의 사용자 ID

        Returns:
            성공 여부
        """
        log_ctx = {
            "method": "UpdateLoginTime",
            "user_id": user_id,
            "provider": provider,
        }

        if self._circuit_breaker.current_state.name == "OPEN":
            logger.warning(
                "Circuit breaker is open, failing fast",
                extra={**log_ctx, "circuit_state": "OPEN"},
            )
            return False

        try:
            stub = await self._get_stub()

            request = users_pb2.UpdateLoginTimeRequest(
                user_id=user_id,
                provider=provider,
                provider_user_id=provider_user_id,
            )

            async def call_func():
                return await stub.UpdateLoginTime(request, timeout=self.timeout)

            response = await self._circuit_breaker.call_async(
                self._call_with_retry, call_func, log_ctx
            )

            logger.info(
                "gRPC UpdateLoginTime succeeded",
                extra={**log_ctx, "success": response.success},
            )
            return response.success

        except (CircuitBreakerError, grpc.aio.AioRpcError, Exception):
            return False

    async def close(self) -> None:
        """Close the gRPC channel."""
        if self._channel:
            await self._channel.close()
            logger.debug("gRPC channel closed", extra={"service": "users.UsersService"})
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


# Singleton instance
_client: UsersGrpcClient | None = None


def get_users_client() -> UsersGrpcClient:
    """Get the singleton UsersGrpcClient instance."""
    global _client
    if _client is None:
        from apps.auth.setup.config import get_settings

        _client = UsersGrpcClient(get_settings())
    return _client


def reset_users_client() -> None:
    """Reset the singleton client (for testing)."""
    global _client
    _client = None


async def close_users_client() -> None:
    """Close the singleton gRPC client channel (for shutdown)."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
