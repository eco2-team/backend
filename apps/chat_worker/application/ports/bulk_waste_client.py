"""대형폐기물 수거 API 클라이언트 Port.

대형폐기물 수거 신청 정보 조회를 위한 추상 인터페이스.

Clean Architecture:
- Port: 이 파일 (추상 인터페이스)
- Adapter: infrastructure/integrations/bulk_waste/

데이터 소스:
- 행정안전부 생활쓰레기배출정보 API (data.go.kr/data/15155080)
- 서울시 열린데이터광장 (data.seoul.go.kr)
- 지자체별 대형폐기물 배출 정보

API 문서:
- https://www.data.go.kr/data/15155080/openapi.do
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WasteType(str, Enum):
    """폐기물 유형."""

    GENERAL = "general"  # 생활쓰레기
    FOOD = "food"  # 음식물쓰레기
    RECYCLABLE = "recyclable"  # 재활용품
    BULK = "bulk"  # 대형폐기물


class DisposalMethod(str, Enum):
    """배출 방법."""

    BAG = "bag"  # 종량제 봉투
    STICKER = "sticker"  # 스티커 부착
    APPOINTMENT = "appointment"  # 수거 예약
    STATION = "station"  # 배출함/거점
    OTHER = "other"  # 기타


@dataclass(frozen=True)
class WasteDisposalInfoDTO:
    """폐기물 배출 정보 DTO.

    행정안전부 API 응답을 Application Layer용 DTO로 변환.

    Attributes:
        region_code: 개방자치단체코드
        sido: 시도명
        sigungu: 시군구명
        dong: 동/읍/면명 (선택)
        disposal_location_type: 배출장소유형
        general_waste_method: 생활쓰레기 배출방법
        food_waste_method: 음식물쓰레기 배출방법
        recyclable_schedule: 재활용품 배출요일
        bulk_waste_method: 대형폐기물 배출방법
        management_dept: 관리부서명
        contact: 연락처
        data_date: 데이터기준일자 (YYYYMMDD)
    """

    region_code: str
    sido: str
    sigungu: str
    dong: str | None = None
    disposal_location_type: str | None = None
    general_waste_method: str | None = None
    food_waste_method: str | None = None
    recyclable_schedule: str | None = None
    bulk_waste_method: str | None = None
    management_dept: str | None = None
    contact: str | None = None
    data_date: str | None = None

    @property
    def full_address(self) -> str:
        """전체 주소 반환."""
        parts = [self.sido, self.sigungu]
        if self.dong:
            parts.append(self.dong)
        return " ".join(parts)


@dataclass(frozen=True)
class BulkWasteItemDTO:
    """대형폐기물 품목 정보 DTO.

    지자체별 대형폐기물 수수료 정보.

    Attributes:
        item_name: 품목명 (예: "소파(3인용)")
        category: 품목 카테고리 (예: "가구류")
        fee: 수수료 (원)
        size_info: 크기 정보 (선택)
        note: 비고
    """

    item_name: str
    category: str
    fee: int
    size_info: str | None = None
    note: str | None = None

    @property
    def fee_text(self) -> str:
        """수수료를 읽기 좋은 형태로 반환."""
        return f"{self.fee:,}원"


@dataclass(frozen=True)
class BulkWasteCollectionDTO:
    """대형폐기물 수거 정보 DTO.

    Attributes:
        sigungu: 시군구명
        application_url: 신청 URL
        application_phone: 신청 전화번호
        collection_method: 수거 방식 설명
        fee_payment_method: 수수료 납부 방법
        items: 품목별 수수료 정보 (선택)
    """

    sigungu: str
    application_url: str | None = None
    application_phone: str | None = None
    collection_method: str | None = None
    fee_payment_method: str | None = None
    items: list[BulkWasteItemDTO] = field(default_factory=list)


@dataclass
class WasteInfoSearchResponse:
    """폐기물 정보 검색 응답.

    Attributes:
        results: 검색 결과 목록
        total_count: 전체 결과 수
        page: 현재 페이지
        page_size: 페이지 크기
        query: 검색 조건
    """

    results: list[WasteDisposalInfoDTO] = field(default_factory=list)
    total_count: int = 0
    page: int = 1
    page_size: int = 10
    query: dict[str, Any] = field(default_factory=dict)

    @property
    def has_next(self) -> bool:
        """다음 페이지 존재 여부."""
        return self.page * self.page_size < self.total_count


class BulkWasteClientPort(ABC):
    """대형폐기물 수거 API 클라이언트 Port.

    다양한 데이터 소스를 추상화:
    - 행정안전부 생활쓰레기배출정보 API
    - 서울시 열린데이터 (예정)
    - 지자체별 API (예정)

    Infrastructure Layer에서 HTTP 구현체 제공.
    """

    @abstractmethod
    async def search_disposal_info(
        self,
        sido: str | None = None,
        sigungu: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> WasteInfoSearchResponse:
        """폐기물 배출 정보 검색.

        행정안전부 API 기반 - 지역별 배출 방법/요일 정보 조회.

        Args:
            sido: 시도명 (예: "서울특별시")
            sigungu: 시군구명 (예: "강남구")
            page: 페이지 번호
            page_size: 한 페이지 결과 수 (최대 100)

        Returns:
            WasteInfoSearchResponse
        """
        pass

    @abstractmethod
    async def get_bulk_waste_info(
        self,
        sigungu: str,
    ) -> BulkWasteCollectionDTO | None:
        """대형폐기물 수거 정보 조회.

        지자체별 대형폐기물 배출 신고/수거 정보.

        Args:
            sigungu: 시군구명 (예: "강남구", "성동구")

        Returns:
            BulkWasteCollectionDTO or None if not found
        """
        pass

    @abstractmethod
    async def search_bulk_waste_fee(
        self,
        sigungu: str,
        item_name: str,
    ) -> list[BulkWasteItemDTO]:
        """대형폐기물 품목별 수수료 검색.

        Args:
            sigungu: 시군구명
            item_name: 품목명 (예: "소파", "냉장고")

        Returns:
            매칭되는 품목 수수료 목록
        """
        pass

    async def close(self) -> None:
        """리소스 정리 (선택적 구현)."""
        pass


__all__ = [
    "WasteType",
    "DisposalMethod",
    "WasteDisposalInfoDTO",
    "BulkWasteItemDTO",
    "BulkWasteCollectionDTO",
    "WasteInfoSearchResponse",
    "BulkWasteClientPort",
]
