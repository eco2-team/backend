"""재활용자원 가격 정보 Port.

재활용가능자원 가격 조회를 위한 추상 인터페이스.

Clean Architecture:
- Port: 이 파일 (추상 인터페이스)
- Adapter: infrastructure/integrations/recyclable_price/

데이터 소스:
- 한국환경공단 재활용가능자원 가격조사 (data.go.kr/data/3076421)
- 매월 10일경 조사, CSV 파일 형태로 공개
- 26개 품목, 8개 권역

API 문서:
- https://www.data.go.kr/data/3076421/fileData.do
- https://www.recycling-info.or.kr/sds/marketIndex.do
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


class RecyclableCategory(str, Enum):
    """재활용품 카테고리."""

    PAPER = "paper"  # 폐지
    PLASTIC = "plastic"  # 폐플라스틱
    GLASS = "glass"  # 폐유리병
    METAL = "metal"  # 폐금속
    TIRE = "tire"  # 폐타이어


class RecyclableRegion(str, Enum):
    """권역 구분."""

    CAPITAL = "capital"  # 수도권
    GANGWON = "gangwon"  # 강원
    CHUNGBUK = "chungbuk"  # 충북
    CHUNGNAM = "chungnam"  # 충남
    JEONBUK = "jeonbuk"  # 전북
    JEONNAM = "jeonnam"  # 전남
    GYEONGBUK = "gyeongbuk"  # 경북
    GYEONGNAM = "gyeongnam"  # 경남
    NATIONAL = "national"  # 전국 평균


# 권역 한글 매핑
REGION_NAMES: dict[RecyclableRegion, str] = {
    RecyclableRegion.CAPITAL: "수도권",
    RecyclableRegion.GANGWON: "강원",
    RecyclableRegion.CHUNGBUK: "충북",
    RecyclableRegion.CHUNGNAM: "충남",
    RecyclableRegion.JEONBUK: "전북",
    RecyclableRegion.JEONNAM: "전남",
    RecyclableRegion.GYEONGBUK: "경북",
    RecyclableRegion.GYEONGNAM: "경남",
    RecyclableRegion.NATIONAL: "전국",
}


@dataclass(frozen=True)
class RecyclablePriceDTO:
    """재활용자원 가격 DTO.

    Attributes:
        item_code: 품목 코드 (예: "PAPER_001")
        item_name: 품목명 (예: "신문지")
        category: 카테고리 (paper, plastic, glass, metal, tire)
        price_per_kg: kg당 가격 (원)
        region: 권역
        survey_date: 조사일 (YYYY-MM)
        unit: 단위 (기본: 원/kg)
        form: 형태 (압축, 플레이크, 펠렛, 잉고트 등)
        note: 비고
    """

    item_code: str
    item_name: str
    category: RecyclableCategory
    price_per_kg: int
    region: RecyclableRegion = RecyclableRegion.NATIONAL
    survey_date: str | None = None  # YYYY-MM
    unit: str = "원/kg"
    form: str | None = None  # 압축, 플레이크, 펠렛, 잉고트
    note: str | None = None

    @property
    def price_text(self) -> str:
        """가격을 읽기 좋은 형태로 반환."""
        return f"{self.price_per_kg:,}{self.unit}"

    @property
    def display_name(self) -> str:
        """표시용 품목명 (형태 포함)."""
        if self.form:
            return f"{self.item_name} ({self.form})"
        return self.item_name


@dataclass
class RecyclablePriceSearchResponse:
    """재활용자원 가격 검색 응답.

    Attributes:
        items: 검색된 품목 목록
        query: 검색 쿼리
        survey_date: 조사 기준일
        region: 검색 권역
        total_count: 전체 결과 수
    """

    items: list[RecyclablePriceDTO] = field(default_factory=list)
    query: str = ""
    survey_date: str | None = None
    region: RecyclableRegion | None = None
    total_count: int = 0

    @property
    def has_results(self) -> bool:
        """결과 존재 여부."""
        return len(self.items) > 0


@dataclass(frozen=True)
class RecyclablePriceTrendDTO:
    """재활용자원 가격 추이 DTO.

    Attributes:
        item_name: 품목명
        region: 권역
        prices: 월별 가격 목록 [(YYYY-MM, price), ...]
        change_rate: 전월 대비 변동률 (%)
        trend: 추세 (up, down, stable)
    """

    item_name: str
    region: RecyclableRegion
    prices: list[tuple[str, int]] = field(default_factory=list)  # [(YYYY-MM, price)]
    change_rate: float | None = None
    trend: str = "stable"  # up, down, stable


@runtime_checkable
class RecyclablePriceClientPort(Protocol):
    """재활용자원 가격 정보 클라이언트 Port.

    데이터 소스:
    - 한국환경공단 재활용가능자원 가격조사 (CSV)
    - 매월 갱신 (10일경)

    Infrastructure Layer에서 파일/캐시 기반 구현체 제공.
    """

    async def search_price(
        self,
        item_name: str,
        region: RecyclableRegion | None = None,
    ) -> RecyclablePriceSearchResponse:
        """품목명으로 가격 검색.

        Args:
            item_name: 품목명 (예: "캔", "신문지", "페트병")
            region: 권역 (None이면 전국 평균)

        Returns:
            RecyclablePriceSearchResponse
        """
        ...

    async def get_category_prices(
        self,
        category: RecyclableCategory,
        region: RecyclableRegion | None = None,
    ) -> RecyclablePriceSearchResponse:
        """카테고리별 전체 가격 조회.

        Args:
            category: 카테고리 (paper, plastic, glass, metal, tire)
            region: 권역 (None이면 전국 평균)

        Returns:
            RecyclablePriceSearchResponse
        """
        ...

    async def get_all_prices(
        self,
        region: RecyclableRegion | None = None,
    ) -> RecyclablePriceSearchResponse:
        """전체 품목 가격 조회.

        Args:
            region: 권역 (None이면 전국 평균)

        Returns:
            RecyclablePriceSearchResponse
        """
        ...


__all__ = [
    "RecyclableCategory",
    "RecyclableRegion",
    "REGION_NAMES",
    "RecyclablePriceDTO",
    "RecyclablePriceSearchResponse",
    "RecyclablePriceTrendDTO",
    "RecyclablePriceClientPort",
]
