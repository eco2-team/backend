"""LocalRecyclablePriceClient 단위 테스트.

YAML 기반 재활용자원 시세 클라이언트 테스트.

테스트 대상:
- YAML 데이터 파싱
- 품목 검색 (정확/동의어/부분 매칭)
- 권역별 가격 조회
- context 문자열 생성
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chat_worker.application.ports.recyclable_price_client import (
    RecyclableCategory,
    RecyclableRegion,
)
from chat_worker.infrastructure.integrations.recyclable_price import (
    LocalRecyclablePriceClient,
)


class TestLocalRecyclablePriceClient:
    """LocalRecyclablePriceClient 테스트 스위트."""

    @pytest.fixture
    def client(self) -> LocalRecyclablePriceClient:
        """테스트용 클라이언트 (실제 YAML 데이터 사용)."""
        return LocalRecyclablePriceClient()

    @pytest.fixture
    def data_path(self) -> Path:
        """YAML 데이터 파일 경로."""
        # test file path: tests/unit/infrastructure/integrations/recyclable_price/test_local_price_client.py
        # target: infrastructure/assets/data/recyclable_prices.yaml
        # From tests/unit/infrastructure/integrations/recyclable_price -> chat_worker
        # then -> infrastructure/assets/data/recyclable_prices.yaml
        return (
            Path(__file__).parent.parent.parent.parent.parent.parent
            / "infrastructure"
            / "assets"
            / "data"
            / "recyclable_prices.yaml"
        )

    # ==========================================================
    # YAML 데이터 로드 테스트
    # ==========================================================

    def test_yaml_file_exists(self, data_path: Path):
        """YAML 데이터 파일 존재 확인."""
        assert data_path.exists(), f"YAML 파일이 없습니다: {data_path}"

    def test_load_data_success(self, client: LocalRecyclablePriceClient):
        """데이터 로드 성공."""
        client._load_data()

        assert client._raw_data is not None
        assert len(client._items) > 0
        assert len(client._synonym_index) > 0

    def test_load_data_builds_indices(self, client: LocalRecyclablePriceClient):
        """인덱스 빌드 확인."""
        client._load_data()

        # 아이템 인덱스
        assert "metal_aluminum_can" in client._item_index
        assert "plastic_pet" in client._item_index

        # 동의어 인덱스 (소문자)
        assert "캔" in client._synonym_index
        assert "페트" in client._synonym_index or "pet" in client._synonym_index

    # ==========================================================
    # 품목 검색 테스트
    # ==========================================================

    @pytest.mark.anyio
    async def test_search_price_exact_match(
        self, client: LocalRecyclablePriceClient
    ):
        """정확한 품목명 검색."""
        response = await client.search_price("알루미늄캔")

        assert response.has_results
        assert response.total_count >= 1
        assert any("알루미늄" in item.item_name for item in response.items)

    @pytest.mark.anyio
    async def test_search_price_synonym_match(
        self, client: LocalRecyclablePriceClient
    ):
        """동의어 검색 (캔 → 철캔, 알루미늄캔)."""
        response = await client.search_price("캔")

        assert response.has_results
        assert response.total_count >= 2  # 철캔, 알루미늄캔
        item_names = [item.item_name for item in response.items]
        assert "철캔" in item_names or "알루미늄캔" in item_names

    @pytest.mark.anyio
    async def test_search_price_synonym_pet(
        self, client: LocalRecyclablePriceClient
    ):
        """동의어 검색 (페트 → PET)."""
        response = await client.search_price("페트")

        assert response.has_results
        assert any("PET" in item.item_name for item in response.items)

    @pytest.mark.anyio
    async def test_search_price_synonym_styrofoam(
        self, client: LocalRecyclablePriceClient
    ):
        """동의어 검색 (스티로폼 → EPS)."""
        response = await client.search_price("스티로폼")

        assert response.has_results
        assert any("EPS" in item.item_name for item in response.items)

    @pytest.mark.anyio
    async def test_search_price_not_found(
        self, client: LocalRecyclablePriceClient
    ):
        """존재하지 않는 품목 검색."""
        response = await client.search_price("없는품목12345")

        assert not response.has_results
        assert response.total_count == 0

    @pytest.mark.anyio
    async def test_search_price_partial_match(
        self, client: LocalRecyclablePriceClient
    ):
        """부분 매칭 검색."""
        response = await client.search_price("플라스틱")

        assert response.has_results
        # 여러 플라스틱 품목이 검색되어야 함
        assert response.total_count >= 1

    # ==========================================================
    # 권역별 가격 테스트
    # ==========================================================

    @pytest.mark.anyio
    async def test_search_price_with_region(
        self, client: LocalRecyclablePriceClient
    ):
        """권역별 가격 조회."""
        # 전국 평균
        response_national = await client.search_price(
            "알루미늄캔", region=RecyclableRegion.NATIONAL
        )
        # 수도권
        response_capital = await client.search_price(
            "알루미늄캔", region=RecyclableRegion.CAPITAL
        )

        assert response_national.has_results
        assert response_capital.has_results

        # 수도권 가격이 전국 평균보다 높아야 함 (데이터 특성상)
        national_price = response_national.items[0].price_per_kg
        capital_price = response_capital.items[0].price_per_kg
        assert capital_price >= national_price

    @pytest.mark.anyio
    async def test_search_price_different_regions(
        self, client: LocalRecyclablePriceClient
    ):
        """여러 권역 가격 비교."""
        regions = [
            RecyclableRegion.NATIONAL,
            RecyclableRegion.CAPITAL,
            RecyclableRegion.GANGWON,
        ]

        prices = {}
        for region in regions:
            response = await client.search_price("신문지", region=region)
            if response.has_results:
                prices[region] = response.items[0].price_per_kg

        # 권역별 가격이 다를 수 있음
        assert len(prices) == 3
        assert all(p > 0 for p in prices.values())

    # ==========================================================
    # 카테고리별 조회 테스트
    # ==========================================================

    @pytest.mark.anyio
    async def test_get_category_prices_metal(
        self, client: LocalRecyclablePriceClient
    ):
        """폐금속류 카테고리 조회."""
        response = await client.get_category_prices(RecyclableCategory.METAL)

        assert response.has_results
        assert response.total_count >= 3  # 철스크랩, 철캔, 알루미늄캔
        assert all(item.category == RecyclableCategory.METAL for item in response.items)

    @pytest.mark.anyio
    async def test_get_category_prices_plastic(
        self, client: LocalRecyclablePriceClient
    ):
        """폐플라스틱류 카테고리 조회."""
        response = await client.get_category_prices(RecyclableCategory.PLASTIC)

        assert response.has_results
        assert response.total_count >= 5  # PE, PP, PS, PET, EPS 등
        assert all(item.category == RecyclableCategory.PLASTIC for item in response.items)

    @pytest.mark.anyio
    async def test_get_category_prices_paper(
        self, client: LocalRecyclablePriceClient
    ):
        """폐지류 카테고리 조회."""
        response = await client.get_category_prices(RecyclableCategory.PAPER)

        assert response.has_results
        assert response.total_count >= 2  # 신문지, 골판지

    @pytest.mark.anyio
    async def test_get_category_prices_glass(
        self, client: LocalRecyclablePriceClient
    ):
        """폐유리병류 카테고리 조회."""
        response = await client.get_category_prices(RecyclableCategory.GLASS)

        assert response.has_results
        assert response.total_count >= 3  # 백색, 갈색, 청녹색

    # ==========================================================
    # 전체 조회 테스트
    # ==========================================================

    @pytest.mark.anyio
    async def test_get_all_prices(self, client: LocalRecyclablePriceClient):
        """전체 품목 조회."""
        response = await client.get_all_prices()

        assert response.has_results
        assert response.total_count >= 15  # 최소 15개 품목
        assert response.query == "all"

    # ==========================================================
    # Context 생성 테스트
    # ==========================================================

    @pytest.mark.anyio
    async def test_build_context_with_results(
        self, client: LocalRecyclablePriceClient
    ):
        """검색 결과로 context 문자열 생성."""
        response = await client.search_price("캔")
        context = client.build_context(response)

        assert len(context) > 0
        assert "재활용자원 시세" in context
        assert "원/kg" in context
        assert "한국환경공단" in context

    @pytest.mark.anyio
    async def test_build_context_empty_results(
        self, client: LocalRecyclablePriceClient
    ):
        """빈 결과로 context 생성 시 빈 문자열."""
        response = await client.search_price("없는품목12345")
        context = client.build_context(response)

        assert context == ""

    @pytest.mark.anyio
    async def test_build_context_with_all_regions(
        self, client: LocalRecyclablePriceClient
    ):
        """모든 권역 포함 context 생성."""
        response = await client.search_price("알루미늄캔")
        context = client.build_context(response, include_all_regions=True)

        assert len(context) > 0
        # 권역별 가격이 포함되어야 함
        assert "권역별" in context or "수도권" in context

    # ==========================================================
    # DTO 변환 테스트
    # ==========================================================

    @pytest.mark.anyio
    async def test_dto_fields(self, client: LocalRecyclablePriceClient):
        """DTO 필드 확인."""
        response = await client.search_price("알루미늄캔")

        assert response.has_results
        item = response.items[0]

        assert item.item_code  # item_id
        assert item.item_name  # 품목명
        assert item.category  # RecyclableCategory
        assert item.price_per_kg > 0  # 가격
        assert item.region  # RecyclableRegion

    @pytest.mark.anyio
    async def test_survey_date_in_response(
        self, client: LocalRecyclablePriceClient
    ):
        """응답에 조사일 포함 확인."""
        response = await client.search_price("캔")

        assert response.survey_date is not None
        assert "2025" in response.survey_date

    # ==========================================================
    # context_id 테스트
    # ==========================================================

    def test_get_context_id(self, client: LocalRecyclablePriceClient):
        """context_id 생성."""
        context_id = client.get_context_id("metal_aluminum_can")

        assert context_id == "recyclable_price:metal_aluminum_can"
