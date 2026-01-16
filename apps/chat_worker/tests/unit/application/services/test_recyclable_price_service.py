"""RecyclablePriceService 단위 테스트.

순수 비즈니스 로직 테스트 (Port 의존 없음).

테스트 대상:
- 가격 정보 포맷팅
- 검색 결과 변환
- 컨텍스트 문자열 생성
- 품목명 추출
"""

from __future__ import annotations

import pytest

from chat_worker.application.ports.recyclable_price_client import (
    RecyclableCategory,
    RecyclablePriceDTO,
    RecyclablePriceSearchResponse,
    RecyclableRegion,
)
from chat_worker.application.services.recyclable_price_service import (
    RecyclablePriceService,
)


class TestRecyclablePriceService:
    """RecyclablePriceService 테스트 스위트."""

    # ==========================================================
    # format_price_result 테스트
    # ==========================================================

    def test_format_price_result_basic(self):
        """기본 가격 정보 포맷팅."""
        price = RecyclablePriceDTO(
            item_code="metal_aluminum_can",
            item_name="알루미늄캔",
            category=RecyclableCategory.METAL,
            price_per_kg=1200,
            region=RecyclableRegion.NATIONAL,
            survey_date="2025-01",
        )

        result = RecyclablePriceService.format_price_result(price)

        assert result["item_name"] == "알루미늄캔"
        assert result["category"] == "metal"
        assert result["price_raw"] == 1200
        assert "1,200" in result["price"]
        assert result["survey_date"] == "2025-01"

    def test_format_price_result_with_form(self):
        """형태 포함 가격 정보 포맷팅."""
        price = RecyclablePriceDTO(
            item_code="plastic_pe_compressed",
            item_name="PE",
            category=RecyclableCategory.PLASTIC,
            price_per_kg=150,
            form="압축",
        )

        result = RecyclablePriceService.format_price_result(price)

        assert result["item_name"] == "PE (압축)"
        assert result["form"] == "압축"

    # ==========================================================
    # format_search_results 테스트
    # ==========================================================

    def test_format_search_results_success(self):
        """검색 결과 포맷팅."""
        response = RecyclablePriceSearchResponse(
            items=[
                RecyclablePriceDTO(
                    item_code="metal_aluminum_can",
                    item_name="알루미늄캔",
                    category=RecyclableCategory.METAL,
                    price_per_kg=1200,
                ),
                RecyclablePriceDTO(
                    item_code="metal_steel_can",
                    item_name="철캔",
                    category=RecyclableCategory.METAL,
                    price_per_kg=180,
                ),
            ],
            query="캔",
            survey_date="2025-01",
            total_count=2,
        )

        result = RecyclablePriceService.format_search_results(response)

        assert result["type"] == "recyclable_prices"
        assert result["query"] == "캔"
        assert result["count"] == 2
        assert result["found"] is True
        assert len(result["items"]) == 2
        assert result["context"]  # context 문자열 존재

    def test_format_search_results_empty(self):
        """빈 검색 결과 포맷팅."""
        response = RecyclablePriceSearchResponse(
            items=[],
            query="없는품목",
            total_count=0,
        )

        result = RecyclablePriceService.format_search_results(response)

        assert result["found"] is False
        assert result["count"] == 0
        assert result["context"] == ""

    # ==========================================================
    # build_context_string 테스트
    # ==========================================================

    def test_build_context_string_with_items(self):
        """아이템 있을 때 컨텍스트 문자열 생성."""
        response = RecyclablePriceSearchResponse(
            items=[
                RecyclablePriceDTO(
                    item_code="metal_aluminum_can",
                    item_name="알루미늄캔",
                    category=RecyclableCategory.METAL,
                    price_per_kg=1200,
                ),
            ],
            query="캔",
            survey_date="2025-01",
            region=RecyclableRegion.NATIONAL,
            total_count=1,
        )

        context = RecyclablePriceService.build_context_string(response)

        assert "재활용자원 시세 정보" in context
        assert "알루미늄캔" in context
        assert "1,200원/kg" in context
        assert "한국환경공단" in context

    def test_build_context_string_empty(self):
        """빈 결과일 때 빈 문자열."""
        response = RecyclablePriceSearchResponse(items=[], query="없음")

        context = RecyclablePriceService.build_context_string(response)

        assert context == ""

    # ==========================================================
    # build_not_found_context 테스트
    # ==========================================================

    def test_build_not_found_context(self):
        """검색 결과 없음 컨텍스트."""
        context = RecyclablePriceService.build_not_found_context("테스트품목")

        assert context["type"] == "not_found"
        assert "테스트품목" in context["message"]
        assert context["query"] == "테스트품목"

    # ==========================================================
    # build_error_context 테스트
    # ==========================================================

    def test_build_error_context(self):
        """에러 컨텍스트 생성."""
        context = RecyclablePriceService.build_error_context("조회 실패")

        assert context["type"] == "error"
        assert context["message"] == "조회 실패"

    # ==========================================================
    # extract_item_name_from_query 테스트
    # ==========================================================

    @pytest.mark.parametrize(
        "message,expected",
        [
            ("캔 얼마야?", "캔"),
            ("페트병 가격 알려줘", "페트"),  # "페트"가 먼저 매칭
            ("신문지 한 kg에 얼마?", "신문지"),
            ("박스 시세 궁금해요", "박스"),
            ("유리병 팔면 얼마 받을 수 있어?", "유리"),
            ("플라스틱 재활용", "플라스틱"),
            ("비닐 얼마에 팔아", "비닐"),
            ("스티로폼 가격", "스티로폼"),
            ("알루미늄 캔 시세", "캔"),  # "캔"이 keywords 리스트에서 먼저 매칭
        ],
    )
    def test_extract_item_name_from_query_success(
        self, message: str, expected: str
    ):
        """키워드 추출 성공."""
        result = RecyclablePriceService.extract_item_name_from_query(message)
        assert result == expected

    def test_extract_item_name_from_query_not_found(self):
        """키워드 추출 실패."""
        result = RecyclablePriceService.extract_item_name_from_query("안녕하세요")
        assert result is None

    def test_extract_item_name_from_query_partial_match(self):
        """부분 매칭 - 페트병 → 페트."""
        result = RecyclablePriceService.extract_item_name_from_query("페트병 버리고 싶어")
        # "페트"가 "페트병"에 포함되어 매칭
        assert result == "페트"

    # ==========================================================
    # format_price_summary 테스트
    # ==========================================================

    def test_format_price_summary_with_items(self):
        """가격 요약 생성."""
        items = [
            RecyclablePriceDTO(
                item_code="metal_aluminum_can",
                item_name="알루미늄캔",
                category=RecyclableCategory.METAL,
                price_per_kg=1200,
            ),
            RecyclablePriceDTO(
                item_code="metal_steel_can",
                item_name="철캔",
                category=RecyclableCategory.METAL,
                price_per_kg=180,
            ),
        ]

        summary = RecyclablePriceService.format_price_summary(items)

        assert "알루미늄캔" in summary
        assert "철캔" in summary

    def test_format_price_summary_empty(self):
        """빈 목록 요약."""
        summary = RecyclablePriceService.format_price_summary([])
        assert "없습니다" in summary

    def test_format_price_summary_truncation(self):
        """5개 초과 시 축약."""
        items = [
            RecyclablePriceDTO(
                item_code=f"item_{i}",
                item_name=f"품목{i}",
                category=RecyclableCategory.PLASTIC,
                price_per_kg=100 * i,
            )
            for i in range(1, 8)  # 7개
        ]

        summary = RecyclablePriceService.format_price_summary(items)

        assert "품목1" in summary
        assert "품목5" in summary
        assert "품목6" not in summary  # 6번째는 표시 안됨
        assert "외 2개" in summary  # 나머지 2개
