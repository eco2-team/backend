"""KECO Collection Point Client 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from chat_worker.infrastructure.integrations.keco import KecoCollectionPointClient


@pytest.fixture
def api_key() -> str:
    """테스트용 API 키."""
    return "test-api-key"


@pytest.fixture
def client(api_key: str) -> KecoCollectionPointClient:
    """테스트용 클라이언트."""
    return KecoCollectionPointClient(api_key=api_key, timeout=5.0)


@pytest.fixture
def mock_response_data() -> dict:
    """모의 API 응답 데이터."""
    return {
        "page": 1,
        "perPage": 10,
        "totalCount": 2,
        "currentCount": 2,
        "matchCount": 2,
        "data": [
            {
                "순번": 1,
                "상호명": "이마트 용산점",
                "수거종류": "폐휴대폰, 소형가전",
                "수거방법": "수거함 설치",
                "수거장소(주소)": "서울특별시 용산구 한강대로 123",
                "장소구분": "대형마트",
                "수거비용": "무료",
            },
            {
                "순번": 2,
                "상호명": "강남구청",
                "수거종류": "폐가전",
                "수거방법": "수거함 설치",
                "수거장소(주소)": "서울특별시 강남구 학동로 426",
                "장소구분": "공공기관",
                "수거비용": "",
            },
        ],
    }


class TestKecoCollectionPointClient:
    """KecoCollectionPointClient 테스트."""

    @pytest.mark.asyncio
    async def test_search_collection_points_success(
        self, client: KecoCollectionPointClient, mock_response_data: dict
    ):
        """검색 성공 테스트."""
        mock_response = MagicMock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            result = await client.search_collection_points(
                address_keyword="용산",
                page=1,
                page_size=10,
            )

        assert result.total_count == 2
        assert len(result.results) == 2
        assert result.results[0].name == "이마트 용산점"
        assert result.results[0].address == "서울특별시 용산구 한강대로 123"
        assert "폐휴대폰" in result.results[0].collection_types
        assert result.results[0].is_free is True

    @pytest.mark.asyncio
    async def test_search_collection_points_by_name(
        self, client: KecoCollectionPointClient, mock_response_data: dict
    ):
        """상호명 검색 테스트."""
        mock_response = MagicMock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            result = await client.search_collection_points(
                name_keyword="이마트",
                page=1,
                page_size=10,
            )

        assert result.total_count == 2
        assert result.query.get("name") == "이마트"

    @pytest.mark.asyncio
    async def test_search_collection_points_empty_result(
        self, client: KecoCollectionPointClient
    ):
        """빈 결과 테스트."""
        empty_response = {
            "page": 1,
            "perPage": 10,
            "totalCount": 0,
            "currentCount": 0,
            "matchCount": 0,
            "data": [],
        }

        mock_response = MagicMock()
        mock_response.json.return_value = empty_response
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            result = await client.search_collection_points(
                address_keyword="없는지역",
            )

        assert result.total_count == 0
        assert len(result.results) == 0
        assert result.has_next is False

    @pytest.mark.asyncio
    async def test_search_collection_points_http_error(
        self, client: KecoCollectionPointClient
    ):
        """HTTP 에러 테스트."""
        mock_http_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "Not Found",
            request=MagicMock(),
            response=mock_response,
        )

        with patch.object(client, "_get_client", return_value=mock_http_client):
            result = await client.search_collection_points(
                address_keyword="강남",
            )

        assert result.total_count == 0
        assert len(result.results) == 0

    @pytest.mark.asyncio
    async def test_search_collection_points_timeout(
        self, client: KecoCollectionPointClient
    ):
        """타임아웃 테스트."""
        mock_http_client = AsyncMock()
        mock_http_client.get.side_effect = httpx.TimeoutException("Timeout")

        with patch.object(client, "_get_client", return_value=mock_http_client):
            result = await client.search_collection_points(
                address_keyword="강남",
            )

        assert result.total_count == 0
        assert len(result.results) == 0

    @pytest.mark.asyncio
    async def test_get_nearby_collection_points_not_implemented(
        self, client: KecoCollectionPointClient
    ):
        """주변 검색 미구현 테스트 - NotImplementedError 발생."""
        with pytest.raises(NotImplementedError) as exc_info:
            await client.get_nearby_collection_points(
                lat=37.5665,
                lon=126.9780,
                radius_km=2.0,
            )

        assert "coordinate-based search" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_parse_collection_types(
        self, client: KecoCollectionPointClient
    ):
        """수거종류 파싱 테스트."""
        response_data = {
            "page": 1,
            "perPage": 10,
            "totalCount": 1,
            "data": [
                {
                    "순번": 1,
                    "상호명": "테스트",
                    "수거종류": "폐휴대폰, 소형가전, 에어프라이어",
                    "수거장소(주소)": "서울시 강남구",
                },
            ],
        }

        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            result = await client.search_collection_points()

        # collection_types는 tuple 타입
        assert isinstance(result.results[0].collection_types, tuple)
        assert len(result.results[0].collection_types) == 3
        assert "폐휴대폰" in result.results[0].collection_types
        assert "소형가전" in result.results[0].collection_types
        assert "에어프라이어" in result.results[0].collection_types

    @pytest.mark.asyncio
    async def test_collection_point_dto_properties(self):
        """CollectionPointDTO 속성 테스트."""
        from chat_worker.application.ports.collection_point_client import (
            CollectionPointDTO,
        )

        # 무료 수거함 (collection_types는 tuple)
        dto_free = CollectionPointDTO(
            id=1,
            name="테스트",
            collection_types=("폐휴대폰",),
            fee="무료",
        )
        assert dto_free.is_free is True
        assert dto_free.collection_types_text == "폐휴대폰"

        # 유료 수거함
        dto_paid = CollectionPointDTO(
            id=2,
            name="테스트2",
            collection_types=("대형가전",),
            fee="1,000원",
        )
        assert dto_paid.is_free is False

        # 비용 정보 없음 (기본 무료)
        dto_none = CollectionPointDTO(
            id=3,
            name="테스트3",
            fee=None,
        )
        assert dto_none.is_free is True
        assert dto_none.collection_types_text == "폐전자제품"

    @pytest.mark.asyncio
    async def test_client_close(self, client: KecoCollectionPointClient):
        """클라이언트 종료 테스트."""
        # 클라이언트 초기화
        mock_http_client = AsyncMock()
        client._client = mock_http_client

        await client.close()

        mock_http_client.aclose.assert_called_once()
        assert client._client is None

    @pytest.mark.asyncio
    async def test_has_next_pagination(self):
        """페이지네이션 has_next 테스트."""
        from chat_worker.application.ports.collection_point_client import (
            CollectionPointSearchResponse,
        )

        # 다음 페이지 있음
        response_with_next = CollectionPointSearchResponse(
            results=[],
            total_count=100,
            page=1,
            page_size=10,
        )
        assert response_with_next.has_next is True

        # 다음 페이지 없음
        response_no_next = CollectionPointSearchResponse(
            results=[],
            total_count=10,
            page=1,
            page_size=10,
        )
        assert response_no_next.has_next is False

    def test_safe_int_parsing(self, client: KecoCollectionPointClient):
        """_safe_int 안전한 정수 변환 테스트."""
        # 정상 정수
        assert client._safe_int(123) == 123
        assert client._safe_int(0) == 0

        # 문자열 정수
        assert client._safe_int("456") == 456
        assert client._safe_int("0") == 0

        # None
        assert client._safe_int(None) == 0
        assert client._safe_int(None, default=99) == 99

        # 잘못된 형식
        assert client._safe_int("abc") == 0
        assert client._safe_int("abc", default=-1) == -1
        assert client._safe_int("12.34") == 0  # float 문자열
        assert client._safe_int([1, 2, 3]) == 0  # list
        assert client._safe_int({}) == 0  # dict
