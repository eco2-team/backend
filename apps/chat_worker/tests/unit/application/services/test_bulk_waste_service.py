"""BulkWasteService Unit Tests."""

from dataclasses import dataclass

import pytest

from chat_worker.application.services.bulk_waste_service import BulkWasteService


# Mock DTOs for testing
@dataclass
class MockWasteDisposalInfoDTO:
    """테스트용 WasteDisposalInfoDTO Mock."""

    full_address: str = "서울시 강남구"
    general_waste_method: str = "규격봉투 사용"
    food_waste_method: str = "음식물 전용봉투"
    recyclable_schedule: str = "매주 화/금"
    bulk_waste_method: str = "온라인 신청"
    contact: str = "02-1234-5678"
    management_dept: str = "환경과"


@dataclass
class MockBulkWasteCollectionDTO:
    """테스트용 BulkWasteCollectionDTO Mock."""

    sigungu: str = "강남구"
    application_url: str = "https://gangnam.go.kr"
    application_phone: str = "02-3423-5678"
    collection_method: str = "문전수거"
    fee_payment_method: str = "온라인 결제"


@dataclass
class MockBulkWasteItemDTO:
    """테스트용 BulkWasteItemDTO Mock."""

    item_name: str = "소파"
    category: str = "가구류"
    fee_text: str = "5,000원"
    size_info: str = "2인용 이하"
    note: str = ""


class TestBulkWasteServiceExtractSigungu:
    """시군구 추출 테스트."""

    def test_extract_sigungu_none(self) -> None:
        """위치 정보 없으면 None."""
        result = BulkWasteService.extract_sigungu(None)
        assert result is None

    def test_extract_sigungu_from_address(self) -> None:
        """address 딕셔너리에서 추출."""
        location = {
            "address": {"sigungu": "강남구", "city": "서울시"}
        }

        result = BulkWasteService.extract_sigungu(location)

        assert result == "강남구"

    def test_extract_sigungu_from_address_구(self) -> None:
        """address 딕셔너리의 '구' 키에서 추출."""
        location = {
            "address": {"구": "서초구", "city": "서울시"}
        }

        result = BulkWasteService.extract_sigungu(location)

        assert result == "서초구"

    def test_extract_sigungu_direct_field(self) -> None:
        """직접 sigungu 필드에서 추출."""
        location = {"sigungu": "마포구", "lat": 37.5}

        result = BulkWasteService.extract_sigungu(location)

        assert result == "마포구"

    def test_extract_sigungu_empty_address(self) -> None:
        """비어있는 address."""
        location = {"address": {}}

        result = BulkWasteService.extract_sigungu(location)

        assert result is None


class TestBulkWasteServiceFormatMethods:
    """포맷 메서드 테스트."""

    def test_format_disposal_info(self) -> None:
        """배출 정보 포맷."""
        info = MockWasteDisposalInfoDTO()

        result = BulkWasteService.format_disposal_info(info)

        assert result["type"] == "disposal_info"
        assert result["region"] == "서울시 강남구"
        assert result["general_waste"] == "규격봉투 사용"
        assert result["contact"] == "02-1234-5678"

    def test_format_bulk_waste_collection(self) -> None:
        """수거 정보 포맷."""
        collection = MockBulkWasteCollectionDTO()

        result = BulkWasteService.format_bulk_waste_collection(collection)

        assert result["type"] == "bulk_waste_collection"
        assert result["sigungu"] == "강남구"
        assert result["application_url"] == "https://gangnam.go.kr"
        assert result["collection_method"] == "문전수거"

    def test_format_bulk_waste_fees(self) -> None:
        """수수료 정보 포맷."""
        items = [
            MockBulkWasteItemDTO(item_name="소파", fee_text="5,000원"),
            MockBulkWasteItemDTO(item_name="냉장고", fee_text="10,000원"),
        ]

        result = BulkWasteService.format_bulk_waste_fees(items, "강남구")

        assert result["type"] == "bulk_waste_fees"
        assert result["sigungu"] == "강남구"
        assert result["item_count"] == 2
        assert len(result["items"]) == 2


class TestBulkWasteServiceContextBuilders:
    """컨텍스트 빌더 테스트."""

    def test_build_not_found_context_with_sigungu(self) -> None:
        """지역 있을 때 not found 컨텍스트."""
        result = BulkWasteService.build_not_found_context("강남구")

        assert result["type"] == "not_found"
        assert "강남구" in result["message"]
        assert "찾을 수 없어요" in result["message"]

    def test_build_not_found_context_without_sigungu(self) -> None:
        """지역 없을 때 not found 컨텍스트."""
        result = BulkWasteService.build_not_found_context(None)

        assert result["type"] == "not_found"
        assert "지역 정보가 없어서" in result["message"]

    def test_build_no_location_context(self) -> None:
        """위치 필요 컨텍스트."""
        result = BulkWasteService.build_no_location_context()

        assert result["type"] == "location_required"
        assert "지역마다 달라요" in result["message"]

    def test_build_error_context(self) -> None:
        """에러 컨텍스트."""
        result = BulkWasteService.build_error_context("API 오류 발생")

        assert result["type"] == "error"
        assert result["message"] == "API 오류 발생"


class TestBulkWasteServiceToAnswerContext:
    """통합 응답 컨텍스트 테스트."""

    def test_to_answer_context_empty(self) -> None:
        """빈 컨텍스트."""
        result = BulkWasteService.to_answer_context()

        assert result["type"] == "bulk_waste_info"
        assert result["sigungu"] is None
        assert result["context"] == ""

    def test_to_answer_context_with_collection(self) -> None:
        """수거 정보 포함 컨텍스트."""
        collection = MockBulkWasteCollectionDTO()

        result = BulkWasteService.to_answer_context(
            collection_info=collection,
            sigungu="강남구",
        )

        assert result["type"] == "bulk_waste_info"
        assert result["sigungu"] == "강남구"
        assert "collection" in result
        assert "수거 신청 방법" in result["context"]

    def test_to_answer_context_with_fees(self) -> None:
        """수수료 정보 포함 컨텍스트."""
        items = [
            MockBulkWasteItemDTO(item_name="소파", fee_text="5,000원"),
        ]

        result = BulkWasteService.to_answer_context(
            fee_items=items,
            sigungu="강남구",
        )

        assert "fees" in result
        assert "품목별 수수료" in result["context"]
        assert "소파" in result["context"]


class TestBulkWasteServiceBuildContextString:
    """컨텍스트 문자열 빌드 테스트."""

    def test_build_context_string_empty(self) -> None:
        """빈 입력."""
        result = BulkWasteService.build_context_string()
        assert result == ""

    def test_build_context_string_with_collection(self) -> None:
        """수거 정보 문자열."""
        collection = MockBulkWasteCollectionDTO()

        result = BulkWasteService.build_context_string(
            collection_info=collection,
            sigungu="강남구",
        )

        assert "## 대형폐기물 정보 (강남구)" in result
        assert "### 수거 신청 방법" in result
        assert "온라인 신청" in result
        assert "전화 신청" in result

    def test_build_context_string_with_many_fees(self) -> None:
        """많은 수수료 항목 (10개 초과)."""
        items = [
            MockBulkWasteItemDTO(item_name=f"품목{i}", fee_text=f"{i}000원")
            for i in range(15)
        ]

        result = BulkWasteService.build_context_string(
            fee_items=items,
            sigungu="강남구",
        )

        assert "### 품목별 수수료" in result
        assert "외 5개 품목..." in result  # 15 - 10 = 5

    def test_build_context_string_includes_source(self) -> None:
        """출처 정보 포함."""
        collection = MockBulkWasteCollectionDTO()

        result = BulkWasteService.build_context_string(
            collection_info=collection,
            sigungu="강남구",
        )

        assert "행정안전부" in result
        assert "지역마다 다를 수 있습니다" in result
