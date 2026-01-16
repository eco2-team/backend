"""행정안전부 생활쓰레기배출정보 HTTP 클라이언트.

행정안전부 생활쓰레기배출정보 API의 HTTP 구현체.
- 배출정보 조회: GET /1741000/household_waste_info/info
- 인증: serviceKey (Query Parameter)

Clean Architecture:
- Port: BulkWasteClientPort (application/ports)
- Adapter: MoisWasteInfoHttpClient (이 파일)

API 문서: https://www.data.go.kr/data/15155080/openapi.do
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

from chat_worker.application.ports.bulk_waste_client import (
    BulkWasteClientPort,
    BulkWasteCollectionDTO,
    BulkWasteItemDTO,
    WasteDisposalInfoDTO,
    WasteInfoSearchResponse,
)

logger = logging.getLogger(__name__)

# 기본 설정
DEFAULT_TIMEOUT = 15.0
MAX_RETRIES = 3

# 대형폐기물 수거 정보 (지자체별 정적 데이터)
# TODO: 추후 API 또는 DB로 대체
BULK_WASTE_INFO: dict[str, dict[str, Any]] = {
    "강남구": {
        "application_url": "https://www.gangnam.go.kr/office/waste/index.do",
        "application_phone": "02-3423-5959",
        "collection_method": "온라인 신청 후 스티커 부착 배출",
        "fee_payment_method": "카드결제, 계좌이체, 가상계좌",
    },
    "성동구": {
        "application_url": "https://www.sd.go.kr/main/contents.do?key=1006",
        "application_phone": "02-2286-5114",
        "collection_method": "온라인 신청 후 수거일 지정 배출",
        "fee_payment_method": "카드결제, 가상계좌",
    },
    "서대문구": {
        "application_url": "https://www.sdm.go.kr/civil/print/waste.do",
        "application_phone": "02-330-1234",
        "collection_method": "신고필증 출력 후 품목에 부착하여 배출",
        "fee_payment_method": "카드결제, 가상계좌",
    },
    "마포구": {
        "application_url": "https://www.mapo.go.kr/site/main/content/mapo01030201",
        "application_phone": "02-3153-8600",
        "collection_method": "온라인 신청 후 배출일에 문 앞 배출",
        "fee_payment_method": "카드결제, 계좌이체",
    },
}

# 대형폐기물 품목별 수수료 예시 (강남구 기준)
# TODO: 추후 API 또는 DB로 대체
BULK_WASTE_ITEMS: list[dict[str, Any]] = [
    {"item_name": "소파(1인용)", "category": "가구류", "fee": 6000},
    {"item_name": "소파(2인용)", "category": "가구류", "fee": 10000},
    {"item_name": "소파(3인용 이상)", "category": "가구류", "fee": 15000},
    {"item_name": "침대(싱글)", "category": "가구류", "fee": 10000},
    {"item_name": "침대(더블)", "category": "가구류", "fee": 15000},
    {"item_name": "매트리스(싱글)", "category": "가구류", "fee": 6000},
    {"item_name": "매트리스(더블)", "category": "가구류", "fee": 10000},
    {"item_name": "장롱(1칸)", "category": "가구류", "fee": 8000},
    {"item_name": "장롱(2칸)", "category": "가구류", "fee": 12000},
    {"item_name": "책상", "category": "가구류", "fee": 6000},
    {"item_name": "식탁(4인용)", "category": "가구류", "fee": 8000},
    {"item_name": "의자", "category": "가구류", "fee": 3000},
    {"item_name": "냉장고(200L 미만)", "category": "가전류", "fee": 8000},
    {"item_name": "냉장고(200L 이상)", "category": "가전류", "fee": 12000},
    {"item_name": "세탁기", "category": "가전류", "fee": 8000},
    {"item_name": "에어컨(실내기)", "category": "가전류", "fee": 6000},
    {"item_name": "TV(40인치 미만)", "category": "가전류", "fee": 5000},
    {"item_name": "TV(40인치 이상)", "category": "가전류", "fee": 8000},
    {"item_name": "자전거", "category": "기타", "fee": 5000},
    {"item_name": "유모차", "category": "기타", "fee": 3000},
]


class MoisWasteInfoHttpClient(BulkWasteClientPort):
    """행정안전부 생활쓰레기배출정보 HTTP 클라이언트.

    공공데이터포털 API를 사용한 비동기 HTTP 클라이언트.

    Features:
    - Lazy connection (첫 호출 시 연결)
    - 구조화된 로깅
    - 에러 처리
    - 대형폐기물 정보는 정적 데이터 제공 (API 미제공 시)

    Usage:
        client = MoisWasteInfoHttpClient(api_key="xxx")
        response = await client.search_disposal_info(sido="서울특별시")
        await client.close()
    """

    BASE_URL = "https://apis.data.go.kr/1741000/household_waste_info"

    def __init__(
        self,
        api_key: str,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """초기화.

        Args:
            api_key: 공공데이터포털 인증키 (Decoding Key 사용)
            timeout: 요청 타임아웃 (초)
        """
        self._api_key = api_key
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy HTTP 클라이언트 생성."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                timeout=self._timeout,
            )
            logger.info("MOIS Waste Info HTTP client created")
        return self._client

    async def search_disposal_info(
        self,
        sido: str | None = None,
        sigungu: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> WasteInfoSearchResponse:
        """폐기물 배출 정보 검색.

        Args:
            sido: 시도명 (예: "서울특별시")
            sigungu: 시군구명 (예: "강남구")
            page: 페이지 번호
            page_size: 한 페이지 결과 수 (최대 100)

        Returns:
            WasteInfoSearchResponse
        """
        client = await self._get_client()

        params: dict[str, Any] = {
            "serviceKey": self._api_key,
            "pageNo": page,
            "numOfRows": min(page_size, 100),
            "returnType": "json",
        }

        # 시군구명 필터 (LIKE 검색)
        if sigungu:
            params["cond[SGG_NM::LIKE]"] = sigungu

        try:
            response = await client.get("/info", params=params)
            response.raise_for_status()
            data = response.json()

            result = self._parse_disposal_response(data, sido, sigungu)

            logger.info(
                "MOIS disposal info search completed",
                extra={
                    "sido": sido,
                    "sigungu": sigungu,
                    "total_count": result.total_count,
                    "result_count": len(result.results),
                },
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(
                "MOIS API HTTP error",
                extra={
                    "status_code": e.response.status_code,
                    "sigungu": sigungu,
                    "detail": e.response.text[:200] if e.response.text else "",
                },
            )
            # 빈 응답 반환 (graceful degradation)
            return WasteInfoSearchResponse(
                query={"sido": sido, "sigungu": sigungu}
            )
        except httpx.TimeoutException:
            logger.error(
                "MOIS API timeout",
                extra={"sigungu": sigungu, "timeout": self._timeout},
            )
            return WasteInfoSearchResponse(
                query={"sido": sido, "sigungu": sigungu}
            )
        except Exception as e:
            logger.error(
                "MOIS disposal info search failed",
                extra={"sigungu": sigungu, "error": str(e)},
            )
            return WasteInfoSearchResponse(
                query={"sido": sido, "sigungu": sigungu}
            )

    def _parse_disposal_response(
        self,
        data: dict[str, Any],
        sido: str | None,
        sigungu: str | None,
    ) -> WasteInfoSearchResponse:
        """API 응답을 WasteInfoSearchResponse로 변환.

        Args:
            data: API 응답 JSON
            sido: 시도명 필터
            sigungu: 시군구명 필터

        Returns:
            WasteInfoSearchResponse
        """
        # 응답 구조: {"response": {"header": {...}, "body": {"items": [...], "totalCount": N}}}
        body = data.get("response", {}).get("body", {})
        items = body.get("items", [])
        total_count = body.get("totalCount", 0)

        # items가 단일 객체인 경우 리스트로 변환
        if isinstance(items, dict):
            items = [items]

        results = []
        for item in items:
            # 시도명 필터 (API가 시도 필터를 지원하지 않는 경우)
            if sido and item.get("CTPV_NM", "") != sido:
                continue

            results.append(
                WasteDisposalInfoDTO(
                    region_code=item.get("OPN_ATMY_GRP_CD", ""),
                    sido=item.get("CTPV_NM", ""),
                    sigungu=item.get("SGG_NM", ""),
                    dong=item.get("EMD_NM"),
                    disposal_location_type=item.get("EMSN_PLC_TYPE"),
                    general_waste_method=item.get("LF_WST_EMSN_MTHD"),
                    food_waste_method=item.get("FOD_WST_EMSN_MTHD"),
                    recyclable_schedule=item.get("RCYCL_EMSN_DOW"),
                    bulk_waste_method=item.get("BULK_WST_EMSN_MTHD"),
                    management_dept=item.get("MNG_DEPT_NM"),
                    contact=item.get("MNG_DEPT_TEL"),
                    data_date=item.get("DAT_CRTR_YMD"),
                )
            )

        return WasteInfoSearchResponse(
            results=results,
            total_count=total_count,
            page=1,
            page_size=len(results),
            query={"sido": sido, "sigungu": sigungu},
        )

    async def get_bulk_waste_info(
        self,
        sigungu: str,
    ) -> BulkWasteCollectionDTO | None:
        """대형폐기물 수거 정보 조회.

        현재는 정적 데이터 제공 (API 미제공).
        추후 지자체별 API 연동 예정.

        Args:
            sigungu: 시군구명 (예: "강남구")

        Returns:
            BulkWasteCollectionDTO or None
        """
        # 정적 데이터에서 조회
        info = BULK_WASTE_INFO.get(sigungu)
        if not info:
            logger.warning(
                "Bulk waste info not found",
                extra={"sigungu": sigungu},
            )
            return None

        return BulkWasteCollectionDTO(
            sigungu=sigungu,
            application_url=info.get("application_url"),
            application_phone=info.get("application_phone"),
            collection_method=info.get("collection_method"),
            fee_payment_method=info.get("fee_payment_method"),
        )

    async def search_bulk_waste_fee(
        self,
        sigungu: str,
        item_name: str,
    ) -> list[BulkWasteItemDTO]:
        """대형폐기물 품목별 수수료 검색.

        현재는 정적 데이터 제공 (API 미제공).
        추후 지자체별 API 연동 예정.

        Args:
            sigungu: 시군구명
            item_name: 품목명 (예: "소파", "냉장고")

        Returns:
            매칭되는 품목 수수료 목록
        """
        # 품목명으로 필터링 (부분 매칭)
        item_name_lower = item_name.lower()
        results = []

        for item in BULK_WASTE_ITEMS:
            if item_name_lower in item["item_name"].lower():
                results.append(
                    BulkWasteItemDTO(
                        item_name=item["item_name"],
                        category=item["category"],
                        fee=item["fee"],
                        size_info=item.get("size_info"),
                        note=item.get("note"),
                    )
                )

        logger.info(
            "Bulk waste fee search completed",
            extra={
                "sigungu": sigungu,
                "item_name": item_name,
                "result_count": len(results),
            },
        )

        return results

    async def close(self) -> None:
        """HTTP 클라이언트 종료."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("MOIS Waste Info HTTP client closed")


__all__ = ["MoisWasteInfoHttpClient"]
