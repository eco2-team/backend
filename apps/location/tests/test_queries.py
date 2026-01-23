"""Application Queries 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from location.application.nearby.dto import SearchRequest
from location.application.nearby.queries import GetNearbyCentersQuery
from location.application.nearby.queries.get_center_detail import GetCenterDetailQuery
from location.application.nearby.queries.search_by_keyword import SearchByKeywordQuery
from location.application.nearby.queries.suggest_places import SuggestPlacesQuery
from location.application.ports.kakao_local_client import (
    KakaoPlaceDTO,
    KakaoSearchResponse,
)
from location.domain.entities import NormalizedSite
from location.domain.enums import PickupCategory, StoreCategory

pytestmark = pytest.mark.asyncio


class TestGetNearbyCentersQuery:
    """GetNearbyCentersQuery 테스트."""

    async def test_execute_returns_empty_list(self, mock_location_reader: AsyncMock) -> None:
        """결과 없으면 빈 리스트 반환."""
        mock_location_reader.find_within_radius.return_value = []

        query = GetNearbyCentersQuery(mock_location_reader)
        request = SearchRequest(latitude=37.5665, longitude=126.978)
        result = await query.execute(request)

        assert result == []
        mock_location_reader.find_within_radius.assert_called_once()

    async def test_execute_returns_entries(
        self, mock_location_reader: AsyncMock, sample_site: NormalizedSite
    ) -> None:
        """결과가 있으면 엔트리 반환."""
        mock_location_reader.find_within_radius.return_value = [(sample_site, 1.5)]

        query = GetNearbyCentersQuery(mock_location_reader)
        request = SearchRequest(latitude=37.5665, longitude=126.978)
        result = await query.execute(request)

        assert len(result) == 1
        assert result[0].id == 1
        assert result[0].distance_km == 1.5

    async def test_execute_uses_zoom_policy(self, mock_location_reader: AsyncMock) -> None:
        """줌 레벨에 따라 반경 결정."""
        mock_location_reader.find_within_radius.return_value = []

        query = GetNearbyCentersQuery(mock_location_reader)
        request = SearchRequest(latitude=37.5665, longitude=126.978, zoom=10)
        await query.execute(request)

        call_args = mock_location_reader.find_within_radius.call_args
        assert call_args is not None
        # zoom 10에 대응하는 반경이 사용되었는지 확인
        assert call_args.kwargs["radius_km"] > 0

    async def test_execute_uses_explicit_radius(self, mock_location_reader: AsyncMock) -> None:
        """명시적 반경이 주어지면 그대로 사용."""
        mock_location_reader.find_within_radius.return_value = []

        query = GetNearbyCentersQuery(mock_location_reader)
        request = SearchRequest(latitude=37.5665, longitude=126.978, radius=3000)
        await query.execute(request)

        call_args = mock_location_reader.find_within_radius.call_args
        assert call_args is not None
        assert call_args.kwargs["radius_km"] == 3.0  # 3000m = 3km

    async def test_execute_filters_store_category(
        self, mock_location_reader: AsyncMock, sample_site: NormalizedSite
    ) -> None:
        """store_filter로 필터링."""
        # sample_site는 재활용 센터로 분류됨 (positn_intdc_cn에 "재활용")
        mock_location_reader.find_within_radius.return_value = [(sample_site, 1.5)]

        query = GetNearbyCentersQuery(mock_location_reader)

        # CAFE_BAKERY로 필터링 → 결과 없음
        request = SearchRequest(
            latitude=37.5665,
            longitude=126.978,
            store_filter={StoreCategory.CAFE_BAKERY},
        )
        result = await query.execute(request)
        assert len(result) == 0

    async def test_execute_filters_pickup_category(
        self, mock_location_reader: AsyncMock, sample_site: NormalizedSite
    ) -> None:
        """pickup_filter로 필터링."""
        mock_location_reader.find_within_radius.return_value = [(sample_site, 1.5)]

        query = GetNearbyCentersQuery(mock_location_reader)

        # ELECTRONICS로 필터링 → 결과 없음 (sample_site에 없음)
        request = SearchRequest(
            latitude=37.5665,
            longitude=126.978,
            pickup_filter={PickupCategory.ELECTRONICS},
        )
        result = await query.execute(request)
        assert len(result) == 0

    async def test_execute_no_filter_returns_all(
        self, mock_location_reader: AsyncMock, sample_site: NormalizedSite
    ) -> None:
        """필터 없으면 모든 결과 반환."""
        mock_location_reader.find_within_radius.return_value = [(sample_site, 1.5)]

        query = GetNearbyCentersQuery(mock_location_reader)
        request = SearchRequest(latitude=37.5665, longitude=126.978)
        result = await query.execute(request)

        assert len(result) == 1


class TestSuggestPlacesQuery:
    """SuggestPlacesQuery 테스트."""

    async def test_execute_returns_suggestions(
        self, mock_kakao_client: AsyncMock, sample_kakao_place: KakaoPlaceDTO
    ) -> None:
        """Kakao 결과를 SuggestEntryDTO로 변환."""
        mock_kakao_client.search_keyword.return_value = KakaoSearchResponse(
            places=[sample_kakao_place]
        )

        query = SuggestPlacesQuery(kakao_client=mock_kakao_client)
        result = await query.execute(query="강남 재활용")

        assert len(result) == 1
        assert result[0].place_name == "강남 재활용센터"
        assert result[0].address == "서울 강남구 테헤란로 123"
        assert result[0].latitude == 37.497
        assert result[0].longitude == 127.028
        assert result[0].place_url == "https://place.map.kakao.com/12345"

    async def test_execute_empty_response(self, mock_kakao_client: AsyncMock) -> None:
        """Kakao 결과 없으면 빈 리스트."""
        mock_kakao_client.search_keyword.return_value = KakaoSearchResponse()

        query = SuggestPlacesQuery(kakao_client=mock_kakao_client)
        result = await query.execute(query="존재하지않는장소")

        assert result == []

    async def test_execute_uses_accuracy_sort(self, mock_kakao_client: AsyncMock) -> None:
        """accuracy 정렬로 호출."""
        mock_kakao_client.search_keyword.return_value = KakaoSearchResponse()

        query = SuggestPlacesQuery(kakao_client=mock_kakao_client)
        await query.execute(query="테스트")

        mock_kakao_client.search_keyword.assert_called_once_with(
            query="테스트", size=5, sort="accuracy"
        )

    async def test_execute_fallback_address(self, mock_kakao_client: AsyncMock) -> None:
        """road_address_name 없으면 address_name 사용."""
        place = KakaoPlaceDTO(
            id="999",
            place_name="테스트",
            category_name="",
            category_group_code="",
            category_group_name="",
            phone=None,
            address_name="지번주소",
            road_address_name=None,
            x="127.0",
            y="37.5",
            place_url="",
        )
        mock_kakao_client.search_keyword.return_value = KakaoSearchResponse(places=[place])

        query = SuggestPlacesQuery(kakao_client=mock_kakao_client)
        result = await query.execute(query="테스트")

        assert result[0].address == "지번주소"


class TestSearchByKeywordQuery:
    """SearchByKeywordQuery 테스트."""

    async def test_execute_returns_db_results(
        self,
        mock_location_reader: AsyncMock,
        mock_kakao_client: AsyncMock,
        sample_site: NormalizedSite,
        sample_kakao_place: KakaoPlaceDTO,
    ) -> None:
        """Kakao 좌표로 DB 검색 후 결과 반환."""
        # Kakao가 좌표를 반환
        mock_kakao_client.search_keyword.return_value = KakaoSearchResponse(
            places=[sample_kakao_place]
        )
        # DB에서 해당 좌표 근처 결과
        mock_location_reader.find_within_radius.return_value = [(sample_site, 0.5)]

        query = SearchByKeywordQuery(
            location_reader=mock_location_reader, kakao_client=mock_kakao_client
        )
        result = await query.execute(query="강남 재활용", radius=5000)

        assert len(result) >= 1
        # DB 결과가 포함됨
        db_entry = next((e for e in result if e.source == "keco"), None)
        assert db_entry is not None
        assert db_entry.id == 1

    async def test_execute_empty_kakao_no_db(
        self, mock_location_reader: AsyncMock, mock_kakao_client: AsyncMock
    ) -> None:
        """Kakao 결과 없으면 빈 리스트."""
        mock_kakao_client.search_keyword.return_value = KakaoSearchResponse()
        mock_location_reader.find_within_radius.return_value = []

        query = SearchByKeywordQuery(
            location_reader=mock_location_reader, kakao_client=mock_kakao_client
        )
        result = await query.execute(query="없는장소", radius=5000)

        assert result == []

    async def test_execute_kakao_only_results(
        self,
        mock_location_reader: AsyncMock,
        mock_kakao_client: AsyncMock,
        sample_kakao_place: KakaoPlaceDTO,
    ) -> None:
        """DB 결과 없고 Kakao만 있으면 Kakao 결과 반환."""
        mock_kakao_client.search_keyword.return_value = KakaoSearchResponse(
            places=[sample_kakao_place]
        )
        mock_location_reader.find_within_radius.return_value = []

        query = SearchByKeywordQuery(
            location_reader=mock_location_reader, kakao_client=mock_kakao_client
        )
        result = await query.execute(query="강남 재활용", radius=5000)

        # Kakao 결과가 포함됨 (음수 ID)
        kakao_entry = next((e for e in result if e.id < 0), None)
        assert kakao_entry is not None
        assert kakao_entry.source == "kakao"
        assert kakao_entry.place_url == "https://place.map.kakao.com/12345"

    async def test_execute_deduplicates_nearby(
        self,
        mock_location_reader: AsyncMock,
        mock_kakao_client: AsyncMock,
    ) -> None:
        """DB와 Kakao 결과가 50m 이내면 중복 제거."""
        # 같은 좌표의 장소
        kakao_place = KakaoPlaceDTO(
            id="111",
            place_name="같은장소",
            category_name="",
            category_group_code="",
            category_group_name="",
            phone=None,
            address_name="서울",
            road_address_name=None,
            x="126.978",  # sample_site와 같은 좌표
            y="37.5665",
            place_url="",
            distance="10",
        )
        mock_kakao_client.search_keyword.return_value = KakaoSearchResponse(places=[kakao_place])

        db_site = NormalizedSite(
            id=1,
            source="keco",
            source_key="TEST",
            positn_nm="같은장소",
            positn_pstn_lat=37.5665,
            positn_pstn_lot=126.978,
        )
        mock_location_reader.find_within_radius.return_value = [(db_site, 0.01)]

        query = SearchByKeywordQuery(
            location_reader=mock_location_reader, kakao_client=mock_kakao_client
        )
        result = await query.execute(query="같은장소", radius=5000)

        # 중복 제거되어 Kakao 결과 없음, DB 결과만 존재
        kakao_entries = [e for e in result if e.id < 0]
        assert len(kakao_entries) == 0


class TestGetCenterDetailQuery:
    """GetCenterDetailQuery 테스트."""

    async def test_execute_not_found(
        self, mock_location_reader: AsyncMock, mock_kakao_client: AsyncMock
    ) -> None:
        """ID로 조회 실패 시 None."""
        mock_location_reader.find_by_id.return_value = None

        query = GetCenterDetailQuery(
            location_reader=mock_location_reader, kakao_client=mock_kakao_client
        )
        result = await query.execute(center_id=999)

        assert result is None

    async def test_execute_returns_detail(
        self,
        mock_location_reader: AsyncMock,
        mock_kakao_client: AsyncMock,
        sample_site: NormalizedSite,
    ) -> None:
        """ID로 조회 성공 시 상세 정보 반환."""
        mock_location_reader.find_by_id.return_value = sample_site

        query = GetCenterDetailQuery(
            location_reader=mock_location_reader, kakao_client=mock_kakao_client
        )
        result = await query.execute(center_id=1)

        assert result is not None
        assert result.id == 1
        assert result.name == "서울 재활용 센터"
        assert result.road_address == "서울시 강남구 테헤란로 123"
        assert result.lot_address == "서울시 강남구 역삼동 123"
        assert result.collection_items == "무색페트, 캔, 종이"

    async def test_execute_enriches_with_kakao(
        self,
        mock_location_reader: AsyncMock,
        mock_kakao_client: AsyncMock,
        sample_site: NormalizedSite,
        sample_kakao_place: KakaoPlaceDTO,
    ) -> None:
        """Kakao API로 place_url 보강."""
        mock_location_reader.find_by_id.return_value = sample_site
        mock_kakao_client.search_keyword.return_value = KakaoSearchResponse(
            places=[sample_kakao_place]
        )

        query = GetCenterDetailQuery(
            location_reader=mock_location_reader, kakao_client=mock_kakao_client
        )
        result = await query.execute(center_id=1)

        assert result is not None
        assert result.place_url == "https://place.map.kakao.com/12345"
        assert result.kakao_place_id == "12345"

    async def test_execute_without_kakao_client(
        self, mock_location_reader: AsyncMock, sample_site: NormalizedSite
    ) -> None:
        """Kakao client 없어도 기본 정보 반환."""
        mock_location_reader.find_by_id.return_value = sample_site

        query = GetCenterDetailQuery(location_reader=mock_location_reader, kakao_client=None)
        result = await query.execute(center_id=1)

        assert result is not None
        assert result.id == 1
        assert result.place_url is None

    async def test_execute_kakao_failure_graceful(
        self,
        mock_location_reader: AsyncMock,
        mock_kakao_client: AsyncMock,
        sample_site: NormalizedSite,
    ) -> None:
        """Kakao API 실패 시 기본 정보만 반환."""
        mock_location_reader.find_by_id.return_value = sample_site
        mock_kakao_client.search_keyword.side_effect = Exception("API timeout")

        query = GetCenterDetailQuery(
            location_reader=mock_location_reader, kakao_client=mock_kakao_client
        )
        result = await query.execute(center_id=1)

        assert result is not None
        assert result.place_url is None
        assert result.kakao_place_id is None
