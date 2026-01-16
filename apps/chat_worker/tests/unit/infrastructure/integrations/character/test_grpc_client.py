"""Character gRPC Client 단위 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_worker.infrastructure.integrations.character.grpc_client import (
    CharacterGrpcClient,
)


class TestCharacterGrpcClient:
    """CharacterGrpcClient 테스트."""

    @pytest.fixture
    def client(self):
        """테스트용 클라이언트."""
        return CharacterGrpcClient(host="localhost", port=50051)

    @pytest.fixture
    def mock_response_found(self):
        """캐릭터 발견 응답."""
        response = MagicMock()
        response.found = True
        response.character_name = "플라"
        response.character_type = "플라스틱"
        response.character_dialog = "분리배출 잘했어!"
        response.match_label = "플라스틱"
        return response

    @pytest.fixture
    def mock_response_not_found(self):
        """캐릭터 미발견 응답."""
        response = MagicMock()
        response.found = False
        return response

    # ==========================================================
    # get_character_by_waste_category Tests
    # ==========================================================

    @pytest.mark.asyncio
    async def test_get_character_found(self, client, mock_response_found):
        """캐릭터 조회 성공."""
        mock_stub = AsyncMock()
        mock_stub.GetCharacterByMatch = AsyncMock(return_value=mock_response_found)

        with patch.object(client, "_get_stub", return_value=mock_stub):
            result = await client.get_character_by_waste_category("플라스틱")

        assert result is not None
        assert result.name == "플라"
        assert result.type_label == "플라스틱"
        assert result.dialog == "분리배출 잘했어!"

    @pytest.mark.asyncio
    async def test_get_character_not_found(self, client, mock_response_not_found):
        """캐릭터 미발견."""
        mock_stub = AsyncMock()
        mock_stub.GetCharacterByMatch = AsyncMock(return_value=mock_response_not_found)

        with patch.object(client, "_get_stub", return_value=mock_stub):
            result = await client.get_character_by_waste_category("존재하지않음")

        assert result is None

    @pytest.mark.asyncio
    async def test_grpc_error_returns_none(self, client):
        """gRPC 에러 시 None 반환."""
        import grpc

        mock_stub = AsyncMock()
        error = grpc.aio.AioRpcError(
            code=grpc.StatusCode.UNAVAILABLE,
            initial_metadata=None,
            trailing_metadata=None,
            details="Connection refused",
            debug_error_string=None,
        )
        mock_stub.GetCharacterByMatch = AsyncMock(side_effect=error)

        with patch.object(client, "_get_stub", return_value=mock_stub):
            result = await client.get_character_by_waste_category("플라스틱")

        assert result is None

    # ==========================================================
    # get_catalog Tests
    # ==========================================================

    @pytest.mark.asyncio
    async def test_get_catalog_not_implemented(self, client):
        """카탈로그 조회는 미구현."""
        result = await client.get_catalog()

        assert result == []

    # ==========================================================
    # Connection Tests
    # ==========================================================

    @pytest.mark.asyncio
    async def test_lazy_connection(self, client, mock_response_found):
        """Lazy 연결 테스트."""
        mock_stub = AsyncMock()
        mock_stub.GetCharacterByMatch = AsyncMock(return_value=mock_response_found)

        # 초기에는 채널이 None
        assert client._channel is None

        with patch.object(client, "_get_stub", return_value=mock_stub):
            await client.get_character_by_waste_category("테스트")

    @pytest.mark.asyncio
    async def test_close_connection(self, client):
        """연결 종료."""
        # Mock 채널 설정
        mock_channel = AsyncMock()
        client._channel = mock_channel
        client._stub = MagicMock()

        await client.close()

        mock_channel.close.assert_called_once()
        assert client._channel is None
        assert client._stub is None

    @pytest.mark.asyncio
    async def test_close_when_not_connected(self, client):
        """연결 전 종료 시도."""
        # 에러 없이 완료되어야 함
        await client.close()

        assert client._channel is None

    # ==========================================================
    # Address Configuration Tests
    # ==========================================================

    def test_address_configuration(self):
        """주소 설정 확인."""
        client = CharacterGrpcClient(host="my-host", port=12345)

        assert client._address == "my-host:12345"

    def test_default_configuration(self):
        """기본 설정 확인."""
        client = CharacterGrpcClient()

        assert client._address == "character-api:50051"
