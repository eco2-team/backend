"""재활용자원 가격 로컬 클라이언트.

한국환경공단 재활용가능자원 가격조사 데이터의 로컬 파일 기반 구현체.
- 데이터 소스: CSV 파일 (매월 10일경 갱신)
- 저장 방식: YAML 에셋 파일 (유지보수 용이)

Clean Architecture:
- Port: RecyclablePriceClientPort (application/ports)
- Adapter: LocalRecyclablePriceClient (이 파일)

데이터 갱신:
- 공공데이터포털에서 CSV 다운로드
- scripts/update_recyclable_prices.py로 YAML 변환
- CI/CD 또는 수동 업데이트

API 문서: https://www.data.go.kr/data/3076421/fileData.do
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from chat_worker.application.ports.recyclable_price_client import (
    REGION_NAMES,
    RecyclableCategory,
    RecyclablePriceClientPort,
    RecyclablePriceDTO,
    RecyclablePriceSearchResponse,
    RecyclablePriceTrendDTO,
    RecyclableRegion,
)

logger = logging.getLogger(__name__)

# 품목명 → 카테고리 매핑
ITEM_CATEGORY_MAP: dict[str, RecyclableCategory] = {
    # 폐지류
    "신문지": RecyclableCategory.PAPER,
    "골판지": RecyclableCategory.PAPER,
    # 폐플라스틱류
    "PE": RecyclableCategory.PLASTIC,
    "PP": RecyclableCategory.PLASTIC,
    "PS": RecyclableCategory.PLASTIC,
    "PET": RecyclableCategory.PLASTIC,
    "ABS": RecyclableCategory.PLASTIC,
    "PVC": RecyclableCategory.PLASTIC,
    "EPS": RecyclableCategory.PLASTIC,
    "HDPE": RecyclableCategory.PLASTIC,
    "LDPE": RecyclableCategory.PLASTIC,
    # 폐유리병류
    "유리병": RecyclableCategory.GLASS,
    "백색유리": RecyclableCategory.GLASS,
    "갈색유리": RecyclableCategory.GLASS,
    "청녹색유리": RecyclableCategory.GLASS,
    "컬렛": RecyclableCategory.GLASS,
    # 폐금속류
    "철스크랩": RecyclableCategory.METAL,
    "철캔": RecyclableCategory.METAL,
    "알루미늄캔": RecyclableCategory.METAL,
    "알루미늄": RecyclableCategory.METAL,
    "캔": RecyclableCategory.METAL,
    # 폐타이어류
    "고무분말": RecyclableCategory.TIRE,
    "타이어": RecyclableCategory.TIRE,
}

# 검색어 → 품목 매핑 (동의어 처리)
SEARCH_SYNONYMS: dict[str, list[str]] = {
    "캔": ["철캔", "알루미늄캔"],
    "페트": ["PET"],
    "페트병": ["PET"],
    "비닐": ["PE", "LDPE"],
    "스티로폼": ["EPS"],
    "박스": ["골판지"],
    "종이": ["신문지", "골판지"],
    "유리": ["백색유리", "갈색유리", "청녹색유리"],
    "플라스틱": ["PE", "PP", "PS", "PET"],
}


class LocalRecyclablePriceClient(RecyclablePriceClientPort):
    """재활용자원 가격 로컬 클라이언트.

    YAML 에셋 파일 기반 가격 조회.

    Features:
    - 로컬 파일 기반 (네트워크 불필요)
    - 동의어 검색 지원 (캔 → 철캔, 알루미늄캔)
    - 권역별 가격 조회
    - Lazy loading (첫 호출 시 파일 로드)

    Usage:
        client = LocalRecyclablePriceClient()
        response = await client.search_price("캔", region=RecyclableRegion.CAPITAL)
    """

    def __init__(
        self,
        data_path: Path | str | None = None,
    ):
        """초기화.

        Args:
            data_path: 가격 데이터 YAML 파일 경로 (None이면 기본 에셋)
        """
        if data_path is None:
            # 기본 에셋 경로
            self._data_path = (
                Path(__file__).parent.parent.parent
                / "assets"
                / "data"
                / "recyclable_prices.yaml"
            )
        else:
            self._data_path = Path(data_path)

        self._data: dict[str, Any] | None = None
        self._prices: list[RecyclablePriceDTO] = []

    def _load_data(self) -> None:
        """데이터 로드 (Lazy loading)."""
        if self._data is not None:
            return

        if not self._data_path.exists():
            logger.warning(
                "Recyclable price data not found: %s, using default data",
                self._data_path,
            )
            self._data = self._get_default_data()
        else:
            with open(self._data_path, encoding="utf-8") as f:
                self._data = yaml.safe_load(f)
                logger.info("Recyclable price data loaded: %s", self._data_path)

        # DTO 변환
        self._prices = self._parse_prices(self._data)

    def _get_default_data(self) -> dict[str, Any]:
        """기본 데이터 (파일 없을 때 사용).

        2025년 1월 기준 예시 데이터 (전국 평균).
        실제 운영 시 YAML 파일로 교체.
        """
        return {
            "survey_date": "2025-01",
            "source": "한국환경공단 재활용가능자원 가격조사",
            "items": [
                # 폐지류
                {"code": "PAPER_001", "name": "신문지", "price": 120, "form": None},
                {"code": "PAPER_002", "name": "골판지", "price": 100, "form": None},
                # 폐금속류
                {"code": "METAL_001", "name": "철캔", "price": 350, "form": "압축"},
                {"code": "METAL_002", "name": "알루미늄캔", "price": 1800, "form": "압축"},
                {"code": "METAL_003", "name": "철스크랩", "price": 280, "form": None},
                # 폐플라스틱류
                {"code": "PLASTIC_001", "name": "PET", "price": 450, "form": "압축"},
                {"code": "PLASTIC_002", "name": "PET", "price": 680, "form": "플레이크"},
                {"code": "PLASTIC_003", "name": "PE", "price": 380, "form": "압축"},
                {"code": "PLASTIC_004", "name": "PP", "price": 420, "form": "압축"},
                {"code": "PLASTIC_005", "name": "PS", "price": 350, "form": "압축"},
                {"code": "PLASTIC_006", "name": "EPS", "price": 280, "form": "압축"},
                # 폐유리병류
                {"code": "GLASS_001", "name": "백색유리", "price": 45, "form": "컬렛"},
                {"code": "GLASS_002", "name": "갈색유리", "price": 40, "form": "컬렛"},
                {"code": "GLASS_003", "name": "청녹색유리", "price": 35, "form": "컬렛"},
                # 폐타이어류
                {"code": "TIRE_001", "name": "고무분말", "price": 150, "form": None},
            ],
        }

    def _parse_prices(self, data: dict[str, Any]) -> list[RecyclablePriceDTO]:
        """데이터를 DTO 목록으로 변환."""
        prices = []
        survey_date = data.get("survey_date")

        for item in data.get("items", []):
            name = item.get("name", "")
            category = ITEM_CATEGORY_MAP.get(name, RecyclableCategory.PLASTIC)

            prices.append(
                RecyclablePriceDTO(
                    item_code=item.get("code", ""),
                    item_name=name,
                    category=category,
                    price_per_kg=item.get("price", 0),
                    region=RecyclableRegion.NATIONAL,
                    survey_date=survey_date,
                    form=item.get("form"),
                    note=item.get("note"),
                )
            )

        return prices

    def _match_items(self, query: str) -> list[RecyclablePriceDTO]:
        """검색어로 품목 매칭.

        동의어 처리 및 부분 매칭 지원.
        """
        self._load_data()

        query_lower = query.lower().strip()
        matched = []

        # 동의어 확장
        search_terms = [query]
        if query in SEARCH_SYNONYMS:
            search_terms.extend(SEARCH_SYNONYMS[query])

        for price in self._prices:
            for term in search_terms:
                term_lower = term.lower()
                name_lower = price.item_name.lower()

                # 정확 매칭 또는 부분 매칭
                if term_lower == name_lower or term_lower in name_lower:
                    if price not in matched:
                        matched.append(price)
                    break

        return matched

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
        self._load_data()

        matched = self._match_items(item_name)

        # 권역 필터 (현재는 전국 데이터만 지원)
        # TODO: 권역별 데이터 추가 시 필터링

        logger.info(
            "Recyclable price search completed",
            extra={
                "query": item_name,
                "region": region.value if region else "national",
                "count": len(matched),
            },
        )

        return RecyclablePriceSearchResponse(
            items=matched,
            query=item_name,
            survey_date=self._data.get("survey_date") if self._data else None,
            region=region or RecyclableRegion.NATIONAL,
            total_count=len(matched),
        )

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
        self._load_data()

        matched = [p for p in self._prices if p.category == category]

        logger.info(
            "Recyclable category prices fetched",
            extra={
                "category": category.value,
                "region": region.value if region else "national",
                "count": len(matched),
            },
        )

        return RecyclablePriceSearchResponse(
            items=matched,
            query=category.value,
            survey_date=self._data.get("survey_date") if self._data else None,
            region=region or RecyclableRegion.NATIONAL,
            total_count=len(matched),
        )

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
        self._load_data()

        logger.info(
            "All recyclable prices fetched",
            extra={
                "region": region.value if region else "national",
                "count": len(self._prices),
            },
        )

        return RecyclablePriceSearchResponse(
            items=self._prices.copy(),
            query="all",
            survey_date=self._data.get("survey_date") if self._data else None,
            region=region or RecyclableRegion.NATIONAL,
            total_count=len(self._prices),
        )

    async def get_price_trend(
        self,
        item_name: str,
        region: RecyclableRegion | None = None,
        months: int = 6,
    ) -> RecyclablePriceTrendDTO | None:
        """품목 가격 추이 조회.

        현재는 단일 시점 데이터만 지원.
        추후 히스토리 데이터 추가 시 구현.

        Args:
            item_name: 품목명
            region: 권역
            months: 조회 기간 (월)

        Returns:
            RecyclablePriceTrendDTO or None
        """
        # TODO: 히스토리 데이터 추가 시 구현
        logger.warning(
            "Price trend not yet implemented",
            extra={"item_name": item_name},
        )
        return None


__all__ = ["LocalRecyclablePriceClient"]
