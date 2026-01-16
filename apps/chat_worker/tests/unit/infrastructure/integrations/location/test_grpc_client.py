"""Location gRPC Client 단위 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_worker.application.ports.location_client import LocationDTO
from chat_worker.infrastructure.integrations.location.grpc_client import (
    LocationGrpcClient,
)


class TestLocationGrpcClient:
    """LocationGrpcClient 테스트."""

    @pytest.fixture
    def client(self):
        """테스트용 클라이언트."""
        return LocationGrpcClient(host="localhost", port=50051)

    @pytest.fixture
    def mock_entry(self):
        """Mock 위치 엔트리."""
        entry = MagicMock()
        entry.id = 1
        entry.name = "강남 재활용 센터"
        entry.road_address = "서울시 강남구 테헤란로 123"
        entry.latitude = 37.5665
        entry.longitude = 126.9780
        entry.distance_km = 1.5
        entry.distance_text = "1.5km"
        entry.store_category = "재활용센터"
        entry.pickup_categories = ["플라스틱", "종이", "캔"]
        entry.is_open = True
        entry.phone = "02-1234-5678"
        return entry

    @pytest.fixture
    def mock_response(self, mock_entry):
        """검색 응답."""
        response = MagicMock()
        response.entries = [mock_entry]
        return response

    @pytest.fixture
    def mock_empty_response(self):
        """빈 검색 응답."""
        response = MagicMock()
        response.entries = []
        return response

    # ==========================================================
    # search_recycling_centers Tests
    # ==========================================================

    @pytest.mark.asyncio
    async def test_search_recycling_centers_found(self, client, mock_response):
        """재활용 센터 검색 성공."""
        mock_stub = AsyncMock()
        mock_stub.SearchNearby = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_stub", return_value=mock_stub):
            result = await client.search_recycling_centers(
                lat=37.5665,
                lon=126.9780,
            )

        assert len(result) == 1
        assert result[0].name == "강남 재활용 센터"
        assert result[0].distance_km == 1.5
        assert "플라스틱" in result[0].pickup_categories

    @pytest.mark.asyncio
    async def test_search_recycling_centers_empty(self, client, mock_empty_response):
        """검색 결과 없음."""
        mock_stub = AsyncMock()
        mock_stub.SearchNearby = AsyncMock(return_value=mock_empty_response)

        with patch.object(client, "_get_stub", return_value=mock_stub):
            result = await client.search_recycling_centers(lat=0, lon=0)

        assert result == []

    @pytest.mark.asyncio
    async def test_search_with_params(self, client, mock_response):
        """파라미터 전달 확인."""
        mock_stub = AsyncMock()
        mock_stub.SearchNearby = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_stub", return_value=mock_stub):
            await client.search_recycling_centers(
                lat=37.5,
                lon=127.0,
                radius=3000,
                limit=5,
            )

        # 호출 확인
        mock_stub.SearchNearby.assert_called_once()

    @pytest.mark.asyncio
    async def test_grpc_error_returns_empty(self, client):
        """gRPC 에러 시 빈 리스트."""
        import grpc

        mock_stub = AsyncMock()
        error = grpc.aio.AioRpcError(
            code=grpc.StatusCode.UNAVAILABLE,
            initial_metadata=None,
            trailing_metadata=None,
            details="Connection refused",
            debug_error_string=None,
        )
        mock_stub.SearchNearby = AsyncMock(side_effect=error)

        with patch.object(client, "_get_stub", return_value=mock_stub):
            result = await client.search_recycling_centers(lat=37.5, lon=127.0)

        assert result == []

    # ==========================================================
    # DTO Conversion Tests
    # ==========================================================

    @pytest.mark.asyncio
    async def test_dto_conversion(self, client, mock_response):
        """DTO 변환 확인."""
        mock_stub = AsyncMock()
        mock_stub.SearchNearby = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_stub", return_value=mock_stub):
            result = await client.search_recycling_centers(lat=37.5, lon=127.0)

        dto = result[0]
        assert isinstance(dto, LocationDTO)
        assert dto.id == 1
        assert dto.name == "강남 재활용 센터"
        assert dto.road_address == "서울시 강남구 테헤란로 123"
        assert dto.is_open is True
        assert dto.phone == "02-1234-5678"

    # ==========================================================
    # Connection Tests
    # ==========================================================

    @pytest.mark.asyncio
    async def test_close_connection(self, client):
        """연결 종료."""
        mock_channel = AsyncMock()
        client._channel = mock_channel
        client._stub = MagicMock()

        await client.close()

        mock_channel.close.assert_called_once()
        assert client._channel is None

    def test_address_configuration(self):
        """주소 설정."""
        client = LocationGrpcClient(host="my-location-api", port=9999)

        assert client._address == "my-location-api:9999"

    def test_default_configuration(self):
        """기본 설정."""
        client = LocationGrpcClient()

        assert client._address == "location-api:50051"
