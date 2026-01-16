"""KECO Collection Point HTTP Client - 한국환경공단 폐전자제품 수거함 API Adapter.

Clean Architecture:
- Port: application/ports/collection_point_client.py
- Adapter: 이 파일 (HTTP 구현)

API 스펙:
- 엔드포인트: https://api.odcloud.kr/api/15106385/v1/uddi:4977d714-dca6-4bda-a10f-9bed30e2ce9c
- 인증: serviceKey 쿼리 파라미터 또는 Authorization 헤더
- 응답: JSON

참고:
- https://www.data.go.kr/data/15106385/fileData.do
- Swagger: https://infuser.odcloud.kr/oas/docs?namespace=15106385/v1
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from chat_worker.application.ports.collection_point_client import (
    CollectionPointClientPort,
    CollectionPointDTO,
    CollectionPointSearchResponse,
)

logger = logging.getLogger(__name__)


class KecoCollectionPointClient(CollectionPointClientPort):
    """한국환경공단 폐전자제품 수거함 API HTTP 클라이언트.

    공공데이터포털 API 구현.

    Attributes:
        BASE_URL: API 기본 URL
        DEFAULT_TIMEOUT: 기본 타임아웃 (초)
    """

    BASE_URL = "https://api.odcloud.kr/api/15106385/v1"
    # 최신 데이터셋 (2024-10-28)
    DATASET_ID = "uddi:4977d714-dca6-4bda-a10f-9bed30e2ce9c"
    DEFAULT_TIMEOUT = 15.0

    def __init__(self, api_key: str, timeout: float = DEFAULT_TIMEOUT):
        """초기화.

        Args:
            api_key: 공공데이터포털 API 키 (Decoding 키 권장)
            timeout: HTTP 타임아웃 (초)
        """
        self._api_key = api_key
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """HTTP 클라이언트 lazy 초기화."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                timeout=self._timeout,
                headers={
                    "Authorization": f"Infuser {self._api_key}",
                },
            )
        return self._client

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        """안전한 정수 변환.

        API 응답의 다양한 타입 (int, str, None)을 안전하게 정수로 변환.

        Args:
            value: 변환할 값
            default: 변환 실패 시 기본값

        Returns:
            정수 값 또는 기본값
        """
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def _parse_collection_point(self, item: dict[str, Any]) -> CollectionPointDTO:
        """API 응답 항목을 DTO로 변환.

        Args:
            item: API 응답의 개별 항목

        Returns:
            CollectionPointDTO
        """
        # 수거종류 파싱 (쉼표로 구분된 문자열) → 불변 tuple로 변환
        collection_types_raw = item.get("수거종류", "")
        collection_types: tuple[str, ...] = ()
        if collection_types_raw:
            # "폐휴대폰, 소형가전" 형태
            collection_types = tuple(
                t.strip() for t in collection_types_raw.split(",") if t.strip()
            )

        return CollectionPointDTO(
            id=self._safe_int(item.get("순번")),
            name=item.get("상호명", ""),
            collection_types=collection_types,
            collection_method=item.get("수거방법"),
            address=item.get("수거장소(주소)"),
            place_category=item.get("장소구분"),
            fee=item.get("수거비용"),
        )

    def _parse_response(
        self,
        data: dict[str, Any],
        query: dict[str, str],
    ) -> CollectionPointSearchResponse:
        """API 응답 파싱.

        Args:
            data: API 응답 JSON
            query: 검색 조건

        Returns:
            CollectionPointSearchResponse
        """
        try:
            # 메타데이터
            page = data.get("page", 1)
            per_page = data.get("perPage", 10)
            total_count = data.get("totalCount", 0)

            # 데이터 항목
            items = data.get("data", [])
            results = [self._parse_collection_point(item) for item in items]

            logger.debug(
                "KECO API response parsed",
                extra={
                    "total_count": total_count,
                    "current_count": len(results),
                    "page": page,
                },
            )

            return CollectionPointSearchResponse(
                results=results,
                total_count=total_count,
                page=page,
                page_size=per_page,
                query=query,
            )

        except (KeyError, ValueError, TypeError) as e:
            logger.error(
                "KECO response parsing error",
                extra={"error": str(e), "data_keys": list(data.keys())},
            )
            return CollectionPointSearchResponse(
                results=[],
                total_count=0,
                page=1,
                page_size=10,
                query=query,
            )

    async def search_collection_points(
        self,
        address_keyword: str | None = None,
        name_keyword: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> CollectionPointSearchResponse:
        """수거함 위치 검색.

        Args:
            address_keyword: 주소 검색어 (예: "강남구", "용산")
            name_keyword: 상호명 검색어 (예: "이마트", "주민센터")
            page: 페이지 번호
            page_size: 한 페이지 결과 수 (최대 1000)

        Returns:
            CollectionPointSearchResponse
        """
        client = await self._get_client()

        # 기본 파라미터
        params: dict[str, Any] = {
            "page": page,
            "perPage": min(page_size, 1000),
            "returnType": "JSON",
        }

        # 검색 조건 추가
        # 공공데이터포털 API는 cond[필드명::LIKE] 형태로 검색 지원
        query: dict[str, str] = {}

        if address_keyword:
            params["cond[수거장소(주소)::LIKE]"] = address_keyword
            query["address"] = address_keyword

        if name_keyword:
            params["cond[상호명::LIKE]"] = name_keyword
            query["name"] = name_keyword

        try:
            logger.debug(
                "KECO API request: search_collection_points",
                extra={
                    "address_keyword": address_keyword,
                    "name_keyword": name_keyword,
                    "page": page,
                    "page_size": page_size,
                },
            )

            response = await client.get(f"/{self.DATASET_ID}", params=params)
            response.raise_for_status()
            data = response.json()

            return self._parse_response(data, query)

        except httpx.HTTPStatusError as e:
            logger.error(
                "KECO API HTTP error",
                extra={
                    "status_code": e.response.status_code,
                    "detail": e.response.text[:200],
                },
            )
            return CollectionPointSearchResponse(
                results=[],
                total_count=0,
                page=page,
                page_size=page_size,
                query=query,
            )
        except httpx.TimeoutException:
            logger.error("KECO API timeout", extra={"timeout": self._timeout})
            return CollectionPointSearchResponse(
                results=[],
                total_count=0,
                page=page,
                page_size=page_size,
                query=query,
            )
        except Exception as e:
            logger.error("KECO API error", extra={"error": str(e)})
            return CollectionPointSearchResponse(
                results=[],
                total_count=0,
                page=page,
                page_size=page_size,
                query=query,
            )

    async def get_nearby_collection_points(
        self,
        lat: float,
        lon: float,
        radius_km: float = 2.0,
        limit: int = 10,
    ) -> list[CollectionPointDTO]:
        """주변 수거함 검색.

        Note:
            한국환경공단 API는 좌표 검색을 지원하지 않습니다.
            이 메서드는 향후 Kakao Local API와 연동하여 구현 예정.

        Args:
            lat: 위도
            lon: 경도
            radius_km: 검색 반경 (km)
            limit: 최대 결과 수

        Raises:
            NotImplementedError: 좌표 기반 검색 미지원
        """
        raise NotImplementedError(
            "KECO API does not support coordinate-based search. "
            "Use search_collection_points with address_keyword instead."
        )

    async def close(self) -> None:
        """HTTP 클라이언트 종료."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.debug("KECO Collection Point HTTP client closed")


__all__ = ["KecoCollectionPointClient"]
