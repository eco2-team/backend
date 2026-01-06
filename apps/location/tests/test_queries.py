"""Application Queries 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from location.application.nearby.dto import SearchRequest
from location.application.nearby.queries import GetNearbyCentersQuery
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
