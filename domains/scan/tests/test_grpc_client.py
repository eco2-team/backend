"""gRPC Client unit tests with retry and circuit breaker."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# grpc는 런타임에만 필요하므로 importorskip 사용
grpc = pytest.importorskip("grpc")


class TestCharacterGrpcClientInit:
    """CharacterGrpcClient 초기화 테스트."""

    def test_initializes_with_settings(self, mock_settings):
        """Settings로 초기화."""
        from domains.scan.core.grpc_client import CharacterGrpcClient

        client = CharacterGrpcClient(mock_settings)

        assert client.target == mock_settings.character_grpc_target
        assert client.timeout == mock_settings.grpc_timeout_seconds
        assert client.max_retries == mock_settings.grpc_max_retries
        assert client._channel is None
        assert client._stub is None

    def test_circuit_breaker_initialized(self, mock_settings):
        """Circuit Breaker가 초기화됨."""
        from domains.scan.core.grpc_client import CharacterGrpcClient

        client = CharacterGrpcClient(mock_settings)

        assert client.circuit_state == "CLOSED"
        assert client.circuit_fail_count == 0


class TestGetStub:
    """_get_stub 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_creates_channel_on_first_call(self, mock_settings):
        """첫 호출 시 채널 생성."""
        from domains.scan.core.grpc_client import CharacterGrpcClient

        client = CharacterGrpcClient(mock_settings)

        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()
            stub = await client._get_stub()

            mock_channel.assert_called_once_with(mock_settings.character_grpc_target)
            assert stub is not None

    @pytest.mark.asyncio
    async def test_reuses_existing_stub(self, mock_settings):
        """이미 존재하는 stub 재사용."""
        from domains.scan.core.grpc_client import CharacterGrpcClient

        client = CharacterGrpcClient(mock_settings)
        mock_stub = MagicMock()
        client._stub = mock_stub

        stub = await client._get_stub()

        assert stub is mock_stub


class TestCallWithRetry:
    """_call_with_retry 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self, mock_settings):
        """첫 시도에 성공."""
        from domains.scan.core.grpc_client import CharacterGrpcClient

        client = CharacterGrpcClient(mock_settings)

        async def success_func():
            return "success"

        result = await client._call_with_retry(success_func, {"test": True})
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retries_on_unavailable(self, mock_settings):
        """UNAVAILABLE 에러 시 재시도."""
        from domains.scan.core.grpc_client import CharacterGrpcClient

        client = CharacterGrpcClient(mock_settings)
        client.retry_base_delay = 0.001  # 테스트 속도를 위해 짧게

        call_count = 0

        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                error = grpc.aio.AioRpcError(
                    code=grpc.StatusCode.UNAVAILABLE,
                    initial_metadata=None,
                    trailing_metadata=None,
                    details="Service unavailable",
                    debug_error_string=None,
                )
                raise error
            return "success"

        result = await client._call_with_retry(flaky_func, {})
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_does_not_retry_on_not_found(self, mock_settings):
        """NOT_FOUND 에러는 재시도하지 않음."""
        from domains.scan.core.grpc_client import CharacterGrpcClient

        client = CharacterGrpcClient(mock_settings)

        async def fail_func():
            error = grpc.aio.AioRpcError(
                code=grpc.StatusCode.NOT_FOUND,
                initial_metadata=None,
                trailing_metadata=None,
                details="Not found",
                debug_error_string=None,
            )
            raise error

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await client._call_with_retry(fail_func, {})

        assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self, mock_settings):
        """최대 재시도 횟수 초과."""
        from domains.scan.core.grpc_client import CharacterGrpcClient

        client = CharacterGrpcClient(mock_settings)
        client.retry_base_delay = 0.001

        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            error = grpc.aio.AioRpcError(
                code=grpc.StatusCode.UNAVAILABLE,
                initial_metadata=None,
                trailing_metadata=None,
                details="Always fails",
                debug_error_string=None,
            )
            raise error

        with pytest.raises(grpc.aio.AioRpcError):
            await client._call_with_retry(always_fail, {})

        # 초기 시도 + 재시도 횟수
        assert call_count == mock_settings.grpc_max_retries + 1


class TestCircuitBreaker:
    """Circuit Breaker 동작 테스트."""

    @pytest.mark.asyncio
    async def test_opens_after_failures(self, mock_settings):
        """연속 실패 후 Circuit Breaker 열림."""
        from domains.scan.core.grpc_client import CharacterGrpcClient

        mock_settings.grpc_circuit_fail_max = 2
        mock_settings.grpc_max_retries = 0  # 재시도 없이 바로 실패
        client = CharacterGrpcClient(mock_settings)
        client._stub = MagicMock()

        # Mock gRPC 호출이 항상 실패
        async def fail_call(*args, **kwargs):
            error = grpc.aio.AioRpcError(
                code=grpc.StatusCode.UNAVAILABLE,
                initial_metadata=None,
                trailing_metadata=None,
                details="Fail",
                debug_error_string=None,
            )
            raise error

        client._stub.GetCharacterReward = fail_call

        # 실패 누적
        for _ in range(mock_settings.grpc_circuit_fail_max):
            result = await client.get_character_reward(MagicMock(), {})
            assert result is None

        # Circuit Breaker가 열림
        assert client.circuit_state == "OPEN"

    @pytest.mark.asyncio
    async def test_fast_fails_when_open(self, mock_settings):
        """Circuit Breaker가 열려있으면 빠른 실패."""
        from aiobreaker import CircuitBreakerState
        from domains.scan.core.grpc_client import CharacterGrpcClient

        client = CharacterGrpcClient(mock_settings)

        # Circuit Breaker 강제로 열기
        client._circuit_breaker._state_storage.state = CircuitBreakerState.OPEN

        result = await client.get_character_reward(MagicMock(), {})

        assert result is None

    def test_reset_circuit_breaker(self, mock_settings):
        """Circuit Breaker 리셋."""
        from domains.scan.core.grpc_client import CharacterGrpcClient

        client = CharacterGrpcClient(mock_settings)

        # 실패 카운터 증가 시뮬레이션
        client._circuit_breaker._state_storage.fail_counter = 3

        client.reset_circuit_breaker()

        assert client.circuit_state == "CLOSED"


class TestClose:
    """close 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_closes_channel(self, mock_settings):
        """채널 닫기."""
        from domains.scan.core.grpc_client import CharacterGrpcClient

        client = CharacterGrpcClient(mock_settings)
        mock_channel = AsyncMock()
        client._channel = mock_channel
        client._stub = MagicMock()

        await client.close()

        mock_channel.close.assert_called_once()
        assert client._channel is None
        assert client._stub is None

    @pytest.mark.asyncio
    async def test_handles_no_channel(self, mock_settings):
        """채널이 없을 때도 에러 없음."""
        from domains.scan.core.grpc_client import CharacterGrpcClient

        client = CharacterGrpcClient(mock_settings)
        assert client._channel is None

        # 에러 없이 완료
        await client.close()


class TestSingleton:
    """싱글톤 패턴 테스트."""

    def test_get_character_client_returns_same_instance(self):
        """같은 인스턴스 반환."""
        from domains.scan.core.grpc_client import (
            get_character_client,
            reset_character_client,
        )

        reset_character_client()

        client1 = get_character_client()
        client2 = get_character_client()

        assert client1 is client2

        reset_character_client()

    def test_reset_clears_singleton(self):
        """리셋 후 새 인스턴스 생성."""
        from domains.scan.core.grpc_client import (
            get_character_client,
            reset_character_client,
        )

        client1 = get_character_client()
        reset_character_client()
        client2 = get_character_client()

        assert client1 is not client2

        reset_character_client()


class TestRetryableStatusCodes:
    """재시도 가능한 상태 코드 테스트."""

    def test_unavailable_is_retryable(self):
        """UNAVAILABLE은 재시도 가능."""
        from domains.scan.core.grpc_client import RETRYABLE_STATUS_CODES

        assert grpc.StatusCode.UNAVAILABLE in RETRYABLE_STATUS_CODES

    def test_deadline_exceeded_is_retryable(self):
        """DEADLINE_EXCEEDED는 재시도 가능."""
        from domains.scan.core.grpc_client import RETRYABLE_STATUS_CODES

        assert grpc.StatusCode.DEADLINE_EXCEEDED in RETRYABLE_STATUS_CODES

    def test_not_found_is_not_retryable(self):
        """NOT_FOUND는 재시도 불가."""
        from domains.scan.core.grpc_client import RETRYABLE_STATUS_CODES

        assert grpc.StatusCode.NOT_FOUND not in RETRYABLE_STATUS_CODES

    def test_invalid_argument_is_not_retryable(self):
        """INVALID_ARGUMENT는 재시도 불가."""
        from domains.scan.core.grpc_client import RETRYABLE_STATUS_CODES

        assert grpc.StatusCode.INVALID_ARGUMENT not in RETRYABLE_STATUS_CODES
