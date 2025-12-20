"""Unit tests for CharacterClient with Circuit Breaker."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from domains.my.core.config import Settings  # noqa: E402
from domains.my.rpc.character_client import CharacterClient, DefaultCharacterInfo  # noqa: E402


@pytest.fixture
def test_settings():
    """Test settings with custom values."""
    return Settings(
        character_grpc_host="localhost",
        character_grpc_port="50051",
        character_grpc_timeout=1.0,
        circuit_fail_max=2,
        circuit_timeout_duration=5,
    )


class TestCharacterClientInit:
    """Tests for CharacterClient initialization."""

    def test_uses_injected_settings(self, test_settings):
        """주입된 Settings 값을 사용합니다."""
        client = CharacterClient(settings=test_settings)

        # 주입된 설정이 적용되었는지 확인
        assert client.settings is test_settings
        assert client.settings.circuit_fail_max == 2

    def test_target_property_with_injected_settings(self, test_settings):
        """주입된 Settings로 _target이 구성됩니다."""
        client = CharacterClient(settings=test_settings)

        assert (
            client._target
            == f"{test_settings.character_grpc_host}:{test_settings.character_grpc_port}"
        )


class TestGetDefaultCharacter:
    """Tests for get_default_character method."""

    @pytest.mark.asyncio
    async def test_returns_character_info_on_success(self, test_settings):
        """성공 시 DefaultCharacterInfo를 반환합니다."""
        client = CharacterClient(settings=test_settings)

        # Mock gRPC response
        mock_response = MagicMock()
        mock_response.found = True
        mock_response.character_id = str(uuid4())
        mock_response.character_code = "ECO_001"
        mock_response.character_name = "이코"
        mock_response.character_type = "default"
        mock_response.character_dialog = "안녕!"

        mock_stub = MagicMock()
        mock_stub.GetDefaultCharacter = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        result = await client.get_default_character()

        assert result is not None
        assert isinstance(result, DefaultCharacterInfo)
        assert result.character_name == "이코"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, test_settings):
        """캐릭터를 찾을 수 없으면 None을 반환합니다."""
        client = CharacterClient(settings=test_settings)

        mock_response = MagicMock()
        mock_response.found = False

        mock_stub = MagicMock()
        mock_stub.GetDefaultCharacter = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        result = await client.get_default_character()

        assert result is None


class TestCircuitBreaker:
    """Tests for Circuit Breaker behavior."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_is_configured(self, test_settings):
        """Circuit Breaker가 설정값으로 구성됩니다."""
        client = CharacterClient(settings=test_settings)

        assert client._circuit_breaker.fail_max == test_settings.circuit_fail_max
        assert client._circuit_breaker.timeout_duration == test_settings.circuit_timeout_duration
        assert client._circuit_breaker.name == "character-grpc-client"

    @pytest.mark.asyncio
    async def test_returns_none_on_grpc_error(self, test_settings):
        """gRPC 에러 시 None을 반환합니다."""
        import grpc

        client = CharacterClient(settings=test_settings)

        # Mock gRPC error
        mock_stub = MagicMock()
        error = grpc.aio.AioRpcError(
            grpc.StatusCode.UNAVAILABLE,
            MagicMock(),
            MagicMock(),
        )
        mock_stub.GetDefaultCharacter = AsyncMock(side_effect=error)
        client._stub = mock_stub

        # 에러 발생 시 None 반환
        result = await client.get_default_character()
        assert result is None

    @pytest.mark.asyncio
    async def test_recovers_after_timeout(self, test_settings):
        """timeout_duration 후 복구를 시도합니다."""
        # 이 테스트는 실제로 timeout을 기다려야 하므로
        # 통합 테스트에서 수행하는 것이 더 적절함
        pass


class TestClose:
    """Tests for close method."""

    @pytest.mark.asyncio
    async def test_closes_channel(self, test_settings):
        """gRPC 채널을 정상적으로 닫습니다."""
        client = CharacterClient(settings=test_settings)

        mock_channel = MagicMock()
        mock_channel.close = AsyncMock()
        client._channel = mock_channel
        client._stub = MagicMock()

        await client.close()

        mock_channel.close.assert_called_once()
        assert client._channel is None
        assert client._stub is None

    @pytest.mark.asyncio
    async def test_close_when_not_connected(self, test_settings):
        """연결되지 않은 상태에서도 안전하게 닫힙니다."""
        client = CharacterClient(settings=test_settings)

        # No exception should be raised
        await client.close()
