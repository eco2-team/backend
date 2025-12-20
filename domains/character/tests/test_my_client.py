"""Tests for MyUserCharacterClient with retry logic."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import grpc
import pytest

from domains.character.rpc.my_client import (
    RETRYABLE_STATUS_CODES,
    MyUserCharacterClient,
    reset_my_client,
)
from domains.character.schemas.catalog import GrantCharacterRequest


class MockSettings:
    """Mock settings for testing."""

    my_grpc_host = "localhost"
    my_grpc_port = 50052
    grpc_timeout_seconds = 1.0
    grpc_max_retries = 3
    grpc_retry_base_delay = 0.01  # Fast retries for testing
    grpc_retry_max_delay = 0.1
    circuit_fail_max = 5
    circuit_timeout_duration = 30


def create_grant_request(user_id=None, character_id=None, **kwargs):
    """Helper to create GrantCharacterRequest for testing."""
    defaults = {
        "user_id": user_id or uuid4(),
        "character_id": character_id or uuid4(),
        "character_code": "ECO001",
        "character_name": "이코",
        "character_type": "default",
        "character_dialog": "안녕하세요!",
        "source": "test",
    }
    defaults.update(kwargs)
    return GrantCharacterRequest(**defaults)


class TestMyUserCharacterClient:
    """Unit tests for MyUserCharacterClient."""

    @pytest.fixture
    def client(self) -> MyUserCharacterClient:
        reset_my_client()
        return MyUserCharacterClient(MockSettings())

    @pytest.fixture
    def user_id(self):
        return uuid4()

    @pytest.fixture
    def character_id(self):
        return uuid4()

    def test_init_with_settings(self, client: MyUserCharacterClient):
        """Test client initialization with settings."""
        assert client.host == "localhost"
        assert client.port == 50052
        assert client.timeout == 1.0
        assert client.max_retries == 3

    @pytest.mark.asyncio
    async def test_grant_character_success(
        self, client: MyUserCharacterClient, user_id, character_id
    ):
        """Test successful grant_character call."""
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.already_owned = False

        mock_stub = AsyncMock()
        mock_stub.GrantCharacter = AsyncMock(return_value=mock_response)

        request = create_grant_request(user_id=user_id, character_id=character_id)

        with patch.object(client, "_get_stub", return_value=mock_stub):
            success, already_owned = await client.grant_character(request)

        assert success is True
        assert already_owned is False
        mock_stub.GrantCharacter.assert_called_once()

    @pytest.mark.asyncio
    async def test_grant_character_already_owned(
        self, client: MyUserCharacterClient, user_id, character_id
    ):
        """Test grant_character when character is already owned."""
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.already_owned = True

        mock_stub = AsyncMock()
        mock_stub.GrantCharacter = AsyncMock(return_value=mock_response)

        request = create_grant_request(
            user_id=user_id,
            character_id=character_id,
            character_type=None,
            character_dialog=None,
        )

        with patch.object(client, "_get_stub", return_value=mock_stub):
            success, already_owned = await client.grant_character(request)

        assert success is True
        assert already_owned is True

    @pytest.mark.asyncio
    async def test_grant_character_retry_on_unavailable(
        self, client: MyUserCharacterClient, user_id, character_id
    ):
        """Test retry logic on UNAVAILABLE status."""
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.already_owned = False

        # First two calls fail, third succeeds
        error = grpc.aio.AioRpcError(
            grpc.StatusCode.UNAVAILABLE,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="Service unavailable",
            debug_error_string="",
        )

        mock_stub = AsyncMock()
        mock_stub.GrantCharacter = AsyncMock(side_effect=[error, error, mock_response])

        request = create_grant_request(
            user_id=user_id,
            character_id=character_id,
            character_dialog="안녕!",
        )

        with patch.object(client, "_get_stub", return_value=mock_stub):
            success, already_owned = await client.grant_character(request)

        assert success is True
        assert already_owned is False
        assert mock_stub.GrantCharacter.call_count == 3

    @pytest.mark.asyncio
    async def test_grant_character_max_retries_exceeded(
        self, client: MyUserCharacterClient, user_id, character_id
    ):
        """Test failure after max retries exceeded."""
        error = grpc.aio.AioRpcError(
            grpc.StatusCode.UNAVAILABLE,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="Service unavailable",
            debug_error_string="",
        )

        mock_stub = AsyncMock()
        mock_stub.GrantCharacter = AsyncMock(side_effect=error)

        request = create_grant_request(
            user_id=user_id,
            character_id=character_id,
            character_dialog="안녕!",
        )

        with patch.object(client, "_get_stub", return_value=mock_stub):
            success, already_owned = await client.grant_character(request)

        # Should return False after all retries fail
        assert success is False
        assert already_owned is False
        # Initial call + 3 retries = 4 calls
        assert mock_stub.GrantCharacter.call_count == 4

    @pytest.mark.asyncio
    async def test_grant_character_no_retry_on_invalid_argument(
        self, client: MyUserCharacterClient, user_id, character_id
    ):
        """Test no retry on non-retryable error (INVALID_ARGUMENT)."""
        error = grpc.aio.AioRpcError(
            grpc.StatusCode.INVALID_ARGUMENT,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="Invalid argument",
            debug_error_string="",
        )

        mock_stub = AsyncMock()
        mock_stub.GrantCharacter = AsyncMock(side_effect=error)

        request = create_grant_request(
            user_id=user_id,
            character_id=character_id,
            character_dialog="안녕!",
        )

        with patch.object(client, "_get_stub", return_value=mock_stub):
            success, already_owned = await client.grant_character(request)

        assert success is False
        assert already_owned is False
        # Should only be called once (no retry)
        assert mock_stub.GrantCharacter.call_count == 1

    @pytest.mark.asyncio
    async def test_close_channel(self, client: MyUserCharacterClient):
        """Test closing the gRPC channel."""
        mock_channel = AsyncMock()
        client._channel = mock_channel
        client._stub = MagicMock()

        await client.close()

        mock_channel.close.assert_called_once()
        assert client._channel is None
        assert client._stub is None


class TestRetryableStatusCodes:
    """Tests for retryable status codes."""

    def test_unavailable_is_retryable(self):
        assert grpc.StatusCode.UNAVAILABLE in RETRYABLE_STATUS_CODES

    def test_deadline_exceeded_is_retryable(self):
        assert grpc.StatusCode.DEADLINE_EXCEEDED in RETRYABLE_STATUS_CODES

    def test_resource_exhausted_is_retryable(self):
        assert grpc.StatusCode.RESOURCE_EXHAUSTED in RETRYABLE_STATUS_CODES

    def test_invalid_argument_not_retryable(self):
        assert grpc.StatusCode.INVALID_ARGUMENT not in RETRYABLE_STATUS_CODES

    def test_not_found_not_retryable(self):
        assert grpc.StatusCode.NOT_FOUND not in RETRYABLE_STATUS_CODES


class TestCircuitBreaker:
    """Tests for Circuit Breaker functionality."""

    @pytest.fixture
    def client(self) -> MyUserCharacterClient:
        reset_my_client()
        client = MyUserCharacterClient(MockSettings())
        client.reset_circuit_breaker()
        return client

    @pytest.fixture
    def user_id(self):
        return uuid4()

    @pytest.fixture
    def character_id(self):
        return uuid4()

    def test_circuit_initial_state_is_closed(self, client: MyUserCharacterClient):
        """Circuit breaker starts in closed state."""
        assert client.circuit_state == "CLOSED"
        assert client.circuit_fail_count == 0

    @pytest.mark.asyncio
    async def test_circuit_opens_after_consecutive_failures(
        self, client: MyUserCharacterClient, user_id, character_id
    ):
        """Circuit breaker opens after fail_max consecutive failures."""
        error = grpc.aio.AioRpcError(
            grpc.StatusCode.UNAVAILABLE,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="Service unavailable",
            debug_error_string="",
        )

        mock_stub = AsyncMock()
        mock_stub.GrantCharacter = AsyncMock(side_effect=error)

        request = create_grant_request(
            user_id=user_id,
            character_id=character_id,
            character_dialog="안녕!",
        )

        with patch.object(client, "_get_stub", return_value=mock_stub):
            # Call enough times to trip the circuit breaker
            for _ in range(client._circuit_fail_max + 1):
                await client.grant_character(request)

        # Circuit should be open after consecutive failures
        assert client.circuit_state == "OPEN"

    @pytest.mark.asyncio
    async def test_circuit_open_fails_fast(
        self, client: MyUserCharacterClient, user_id, character_id
    ):
        """When circuit is open, calls fail fast without making actual request."""
        # Manually set circuit to open state
        client._circuit_breaker.open()

        mock_stub = AsyncMock()

        request = create_grant_request(
            user_id=user_id,
            character_id=character_id,
            character_dialog="안녕!",
        )

        with patch.object(client, "_get_stub", return_value=mock_stub):
            success, already_owned = await client.grant_character(request)

        # Should fail fast
        assert success is False
        assert already_owned is False
        # Stub should never be called when circuit is open
        mock_stub.GrantCharacter.assert_not_called()

    def test_reset_circuit_breaker(self, client: MyUserCharacterClient):
        """Circuit breaker can be reset to closed state."""
        client._circuit_breaker.open()
        assert client.circuit_state == "OPEN"

        client.reset_circuit_breaker()
        assert client.circuit_state == "CLOSED"

    @pytest.mark.asyncio
    async def test_success_resets_fail_counter(
        self, client: MyUserCharacterClient, user_id, character_id
    ):
        """Successful call resets the failure counter."""
        error = grpc.aio.AioRpcError(
            grpc.StatusCode.UNAVAILABLE,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="Service unavailable",
            debug_error_string="",
        )

        mock_response = MagicMock()
        mock_response.success = True
        mock_response.already_owned = False

        mock_stub = AsyncMock()
        # Fail twice, then succeed
        mock_stub.GrantCharacter = AsyncMock(
            side_effect=[error, error, error, error, mock_response]
        )

        request = create_grant_request(
            user_id=user_id,
            character_id=character_id,
            character_dialog="안녕!",
        )

        with patch.object(client, "_get_stub", return_value=mock_stub):
            # This should succeed (after retries)
            success, _ = await client.grant_character(request)

        # Circuit should still be closed after successful call
        assert client.circuit_state == "CLOSED"
