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
    RecyclablePriceDTO,
    RecyclablePriceSearchResponse,
    RecyclablePriceTrendDTO,
    RecyclableRegion,
)

logger = logging.getLogger(__name__)

# Category ID → RecyclableCategory 매핑
CATEGORY_ID_MAP: dict[str, RecyclableCategory] = {
    "paper": RecyclableCategory.PAPER,
    "plastic": RecyclableCategory.PLASTIC,
    "glass": RecyclableCategory.GLASS,
    "metal": RecyclableCategory.METAL,
    "tire": RecyclableCategory.TIRE,
}


class LocalRecyclablePriceClient:
    """재활용자원 가격 로컬 클라이언트.

    YAML 에셋 파일 기반 가격 조회.

    Features:
    - 로컬 파일 기반 (네트워크 불필요)
    - 동의어 검색 지원 (캔 → 철캔, 알루미늄캔)
    - 권역별 가격 조회
    - context 생성 지원 (LLM 프롬프트용)
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

        self._raw_data: dict[str, Any] | None = None
        self._items: list[dict[str, Any]] = []  # 원본 아이템 데이터
        self._synonym_index: dict[str, list[str]] = {}  # 검색어 → item_id 목록
        self._item_index: dict[str, dict[str, Any]] = {}  # item_id → 아이템 데이터

    def _load_data(self) -> None:
        """데이터 로드 (Lazy loading)."""
        if self._raw_data is not None:
            return

        if not self._data_path.exists():
            logger.warning(
                "Recyclable price data not found: %s",
                self._data_path,
            )
            self._raw_data = {}
            return

        with open(self._data_path, encoding="utf-8") as f:
            self._raw_data = yaml.safe_load(f) or {}
            logger.info("Recyclable price data loaded: %s", self._data_path)

        # 인덱스 빌드
        self._build_indices()

    def _build_indices(self) -> None:
        """검색 인덱스 빌드."""
        if not self._raw_data:
            return

        # 카테고리 순회하며 아이템 수집
        for category in self._raw_data.get("categories", []):
            category_id = category.get("id", "")
            category_name = category.get("name", "")

            for item in category.get("items", []):
                item_id = item.get("id", "")
                item_name = item.get("name", "")
                synonyms = item.get("synonyms", [])

                # 아이템 데이터 저장 (카테고리 정보 포함)
                item_data = {
                    **item,
                    "category_id": category_id,
                    "category_name": category_name,
                }
                self._items.append(item_data)
                self._item_index[item_id] = item_data

                # 이름과 동의어를 인덱스에 추가
                name_lower = item_name.lower()
                if name_lower not in self._synonym_index:
                    self._synonym_index[name_lower] = []
                self._synonym_index[name_lower].append(item_id)

                for syn in synonyms:
                    syn_lower = syn.lower()
                    if syn_lower not in self._synonym_index:
                        self._synonym_index[syn_lower] = []
                    if item_id not in self._synonym_index[syn_lower]:
                        self._synonym_index[syn_lower].append(item_id)

        # YAML의 search_synonyms도 인덱스에 추가
        for keyword, item_ids in self._raw_data.get("search_synonyms", {}).items():
            keyword_lower = keyword.lower()
            if keyword_lower not in self._synonym_index:
                self._synonym_index[keyword_lower] = []
            for item_id in item_ids:
                if item_id not in self._synonym_index[keyword_lower]:
                    self._synonym_index[keyword_lower].append(item_id)

        logger.info(
            "Price indices built",
            extra={
                "items_count": len(self._items),
                "synonyms_count": len(self._synonym_index),
            },
        )

    def _get_region_key(self, region: RecyclableRegion | None) -> str:
        """RecyclableRegion → YAML region key 변환."""
        if region is None:
            return "nationwide"

        # RecyclableRegion.value → YAML key
        region_map = {
            "national": "nationwide",
            "capital": "capital",
            "gangwon": "gangwon",
            "chungbuk": "chungbuk",
            "chungnam": "chungnam",
            "jeonbuk": "jeonbuk",
            "jeonnam": "jeonnam",
            "gyeongbuk": "gyeongbuk",
            "gyeongnam": "gyeongnam",
        }
        return region_map.get(region.value, "nationwide")

    def _item_to_dto(
        self,
        item: dict[str, Any],
        region: RecyclableRegion | None = None,
    ) -> RecyclablePriceDTO:
        """아이템 데이터를 DTO로 변환."""
        region_key = self._get_region_key(region)
        prices = item.get("prices", {})
        price = prices.get(region_key, prices.get("nationwide", 0))

        category_id = item.get("category_id", "")
        category = CATEGORY_ID_MAP.get(category_id, RecyclableCategory.PLASTIC)

        survey_info = self._raw_data.get("survey_info", {}) if self._raw_data else {}

        return RecyclablePriceDTO(
            item_code=item.get("id", ""),
            item_name=item.get("name", ""),
            category=category,
            price_per_kg=price,
            region=region or RecyclableRegion.NATIONAL,
            survey_date=survey_info.get("date"),
            form=item.get("form"),
            note=item.get("note"),
        )

    def _search_items(self, query: str) -> list[dict[str, Any]]:
        """검색어로 아이템 검색.

        동의어 인덱스를 사용한 빠른 검색.
        """
        self._load_data()

        query_lower = query.lower().strip()
        matched_items = []
        seen_ids = set()

        # 1. 정확 매칭 (인덱스 사용)
        if query_lower in self._synonym_index:
            for item_id in self._synonym_index[query_lower]:
                if item_id in self._item_index and item_id not in seen_ids:
                    matched_items.append(self._item_index[item_id])
                    seen_ids.add(item_id)

        # 2. 부분 매칭 (인덱스 키 순회)
        if not matched_items:
            for key, item_ids in self._synonym_index.items():
                if query_lower in key or key in query_lower:
                    for item_id in item_ids:
                        if item_id in self._item_index and item_id not in seen_ids:
                            matched_items.append(self._item_index[item_id])
                            seen_ids.add(item_id)

        return matched_items

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

        matched = self._search_items(item_name)
        items = [self._item_to_dto(item, region) for item in matched]

        survey_info = self._raw_data.get("survey_info", {}) if self._raw_data else {}

        logger.info(
            "Recyclable price search completed",
            extra={
                "query": item_name,
                "region": region.value if region else "national",
                "count": len(items),
            },
        )

        return RecyclablePriceSearchResponse(
            items=items,
            query=item_name,
            survey_date=survey_info.get("date"),
            region=region or RecyclableRegion.NATIONAL,
            total_count=len(items),
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

        # category.value → category_id 매핑
        category_id_map = {
            "paper": "paper",
            "plastic": "plastic",
            "glass": "glass",
            "metal": "metal",
            "tire": "tire",
        }
        target_category_id = category_id_map.get(category.value, "")

        matched = [
            item for item in self._items
            if item.get("category_id") == target_category_id
        ]
        items = [self._item_to_dto(item, region) for item in matched]

        survey_info = self._raw_data.get("survey_info", {}) if self._raw_data else {}

        logger.info(
            "Recyclable category prices fetched",
            extra={
                "category": category.value,
                "region": region.value if region else "national",
                "count": len(items),
            },
        )

        return RecyclablePriceSearchResponse(
            items=items,
            query=category.value,
            survey_date=survey_info.get("date"),
            region=region or RecyclableRegion.NATIONAL,
            total_count=len(items),
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

        items = [self._item_to_dto(item, region) for item in self._items]
        survey_info = self._raw_data.get("survey_info", {}) if self._raw_data else {}

        logger.info(
            "All recyclable prices fetched",
            extra={
                "region": region.value if region else "national",
                "count": len(items),
            },
        )

        return RecyclablePriceSearchResponse(
            items=items,
            query="all",
            survey_date=survey_info.get("date"),
            region=region or RecyclableRegion.NATIONAL,
            total_count=len(items),
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

        Raises:
            NotImplementedError: 히스토리 데이터 미지원

        Returns:
            RecyclablePriceTrendDTO or None
        """
        raise NotImplementedError(
            "가격 추이 조회는 아직 지원하지 않습니다. "
            "히스토리 데이터 추가 후 구현 예정입니다."
        )

    # ========== Context 생성 (프롬프트 주입용) ==========

    def build_context(
        self,
        response: RecyclablePriceSearchResponse,
        include_all_regions: bool = False,
    ) -> str:
        """검색 결과를 LLM context 문자열로 변환.

        Args:
            response: 검색 응답
            include_all_regions: 모든 권역 가격 포함 여부

        Returns:
            context 문자열 (프롬프트에 주입)
        """
        if not response.items:
            return ""

        lines = [
            f"## 재활용자원 시세 정보 (조사일: {response.survey_date or '미상'})",
            f"검색어: {response.query}",
            f"기준 권역: {REGION_NAMES.get(response.region, '전국')}",
            "",
        ]

        for item in response.items:
            form_str = f" ({item.form})" if item.form else ""
            lines.append(f"- **{item.item_name}{form_str}**: {item.price_per_kg:,}원/kg")

            # 모든 권역 가격 포함
            if include_all_regions:
                # 원본 아이템에서 모든 권역 가격 가져오기
                if item.item_code in self._item_index:
                    prices = self._item_index[item.item_code].get("prices", {})
                    region_prices = []
                    for region_id, price in prices.items():
                        if region_id != "nationwide":
                            region_name = self._get_region_name(region_id)
                            region_prices.append(f"{region_name} {price:,}원")
                    if region_prices:
                        lines.append(f"  - 권역별: {', '.join(region_prices)}")

        lines.append("")
        lines.append("※ 출처: 한국환경공단 재활용가능자원 가격조사")
        lines.append("※ 가격은 업체별로 상이할 수 있습니다.")

        return "\n".join(lines)

    def _get_region_name(self, region_id: str) -> str:
        """region_id → 한글 권역명."""
        names = {
            "nationwide": "전국",
            "capital": "수도권",
            "gangwon": "강원",
            "chungbuk": "충북",
            "chungnam": "충남",
            "jeonbuk": "전북",
            "jeonnam": "전남",
            "gyeongbuk": "경북",
            "gyeongnam": "경남",
        }
        return names.get(region_id, region_id)

    def get_context_id(self, item_code: str) -> str:
        """아이템 코드로 context_id 생성.

        context_id 형식: recyclable_price:{item_code}
        """
        return f"recyclable_price:{item_code}"


__all__ = ["LocalRecyclablePriceClient"]
