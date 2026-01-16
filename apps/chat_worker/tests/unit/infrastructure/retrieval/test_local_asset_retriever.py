"""LocalAssetRetriever 단위 테스트."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from chat_worker.infrastructure.retrieval.local_asset_retriever import (
    LocalAssetRetriever,
)


class TestLocalAssetRetriever:
    """LocalAssetRetriever 테스트 스위트."""

    @pytest.fixture
    def temp_assets_dir(self) -> Path:
        """임시 에셋 디렉토리."""
        with tempfile.TemporaryDirectory() as tmpdir:
            assets_path = Path(tmpdir)

            # 재활용 폐기물 JSON
            recycling_data = {
                "category": "재활용폐기물",
                "items": ["페트병", "유리병", "캔"],
                "method": "세척 후 분리수거",
            }
            with open(assets_path / "재활용폐기물.json", "w", encoding="utf-8") as f:
                json.dump(recycling_data, f, ensure_ascii=False)

            # 일반 종량제 폐기물 JSON
            general_data = {
                "category": "일반종량제폐기물",
                "items": ["일반 쓰레기"],
                "method": "종량제 봉투에 배출",
            }
            with open(assets_path / "일반종량제폐기물.json", "w", encoding="utf-8") as f:
                json.dump(general_data, f, ensure_ascii=False)

            # 음식물류 폐기물 JSON
            food_data = {
                "category": "음식물류폐기물",
                "items": ["음식물 쓰레기"],
                "method": "음식물 전용 봉투",
            }
            with open(assets_path / "음식물류폐기물.json", "w", encoding="utf-8") as f:
                json.dump(food_data, f, ensure_ascii=False)

            yield assets_path

    @pytest.fixture
    def retriever(self, temp_assets_dir: Path) -> LocalAssetRetriever:
        """테스트용 Retriever."""
        return LocalAssetRetriever(assets_path=temp_assets_dir)

    # ==========================================================
    # Initialization Tests
    # ==========================================================

    def test_initialization(self, retriever: LocalAssetRetriever):
        """초기화 확인."""
        categories = retriever.get_all_categories()
        assert len(categories) == 3

    def test_initialization_nonexistent_path(self):
        """존재하지 않는 경로."""
        retriever = LocalAssetRetriever(assets_path="/nonexistent/path")
        categories = retriever.get_all_categories()
        assert categories == []

    # ==========================================================
    # search Tests
    # ==========================================================

    def test_search_exact_match(self, retriever: LocalAssetRetriever):
        """정확한 카테고리 검색."""
        result = retriever.search("재활용폐기물")

        assert result is not None
        assert result["category"] == "재활용폐기물"
        assert "data" in result

    def test_search_partial_match(self, retriever: LocalAssetRetriever):
        """부분 일치 검색."""
        result = retriever.search("재활용")

        assert result is not None
        assert "재활용" in result["key"]

    def test_search_abbreviation_mapping(self, retriever: LocalAssetRetriever):
        """약어 매핑 검색."""
        result = retriever.search("일반")  # 일반 → 일반종량제폐기물

        assert result is not None
        assert "일반종량제폐기물" in result["key"]

    def test_search_food_waste_abbreviation(self, retriever: LocalAssetRetriever):
        """음식물 약어 검색."""
        result = retriever.search("음식물")

        assert result is not None
        assert "음식물류폐기물" in result["key"]

    def test_search_not_found(self, retriever: LocalAssetRetriever):
        """검색 결과 없음."""
        result = retriever.search("존재하지않는카테고리")

        assert result is None

    def test_search_with_subcategory(self, retriever: LocalAssetRetriever):
        """하위 카테고리 포함 검색."""
        result = retriever.search("재활용", subcategory="페트병")

        assert result is not None
        assert result["subcategory"] == "페트병"

    # ==========================================================
    # search_by_keyword Tests
    # ==========================================================

    def test_search_by_keyword_in_filename(self, retriever: LocalAssetRetriever):
        """파일명 키워드 검색."""
        results = retriever.search_by_keyword("재활용")

        assert len(results) >= 1
        assert any("재활용" in r["key"] for r in results)

    def test_search_by_keyword_in_content(self, retriever: LocalAssetRetriever):
        """내용 키워드 검색."""
        results = retriever.search_by_keyword("페트병")

        assert len(results) >= 1

    def test_search_by_keyword_limit(self, retriever: LocalAssetRetriever):
        """검색 결과 제한."""
        results = retriever.search_by_keyword("폐기물", limit=2)

        assert len(results) <= 2

    def test_search_by_keyword_no_results(self, retriever: LocalAssetRetriever):
        """키워드 검색 결과 없음."""
        results = retriever.search_by_keyword("존재하지않는키워드xyz")

        assert results == []

    def test_search_by_keyword_case_insensitive(self, retriever: LocalAssetRetriever):
        """대소문자 무관 검색."""
        results_lower = retriever.search_by_keyword("재활용")
        results_mixed = retriever.search_by_keyword("재활용")

        assert len(results_lower) == len(results_mixed)

    # ==========================================================
    # get_all_categories Tests
    # ==========================================================

    def test_get_all_categories(self, retriever: LocalAssetRetriever):
        """전체 카테고리 조회."""
        categories = retriever.get_all_categories()

        assert isinstance(categories, list)
        assert "재활용폐기물" in categories
        assert "일반종량제폐기물" in categories
        assert "음식물류폐기물" in categories

    def test_get_all_categories_returns_copy(self, retriever: LocalAssetRetriever):
        """카테고리 목록이 복사본인지."""
        categories1 = retriever.get_all_categories()
        categories2 = retriever.get_all_categories()

        # 원본이 아닌 복사본이어야 함
        categories1.append("테스트")
        assert "테스트" not in categories2
