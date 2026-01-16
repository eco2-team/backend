"""카카오 로컬 HTTP 클라이언트.

카카오 로컬 API의 HTTP 구현체.
- 키워드 검색: GET /v2/local/search/keyword.json
- 카테고리 검색: GET /v2/local/search/category.json
- 인증: Authorization: KakaoAK {REST_API_KEY}

Clean Architecture:
- Port: KakaoLocalClientPort (application/ports)
- Adapter: KakaoLocalHttpClient (이 파일)

API 문서: https://developers.kakao.com/docs/latest/ko/local/dev-guide
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from chat_worker.application.ports.kakao_local_client import (
    KakaoLocalClientPort,
    KakaoPlaceDTO,
    KakaoSearchMeta,
    KakaoSearchResponse,
)

logger = logging.getLogger(__name__)

# 기본 설정
DEFAULT_TIMEOUT = 10.0
MAX_RETRIES = 3
RETRY_DELAY = 1.0


class KakaoLocalHttpClient(KakaoLocalClientPort):
    """카카오 로컬 HTTP 클라이언트.

    httpx AsyncClient를 사용한 비동기 HTTP 클라이언트.

    Features:
    - Lazy connection (첫 호출 시 연결)
    - 자동 재시도
    - 타임아웃 설정
    - 구조화된 로깅
    - 에러 처리

    Usage:
        client = KakaoLocalHttpClient(api_key="xxx")
        response = await client.search_keyword("강남역 카페")
        await client.close()
    """

    BASE_URL = "https://dapi.kakao.com/v2/local/search"

    def __init__(
        self,
        api_key: str,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """초기화.

        Args:
            api_key: 카카오 REST API 키
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
                headers={
                    "Authorization": f"KakaoAK {self._api_key}",
                },
                timeout=self._timeout,
            )
            logger.info("Kakao Local HTTP client created")
        return self._client

    async def search_keyword(
        self,
        query: str,
        x: float | None = None,
        y: float | None = None,
        radius: int = 5000,
        page: int = 1,
        size: int = 15,
        sort: str = "accuracy",
    ) -> KakaoSearchResponse:
        """키워드로 장소 검색.

        Args:
            query: 검색 키워드
            x: 중심 좌표 경도
            y: 중심 좌표 위도
            radius: 검색 반경 (미터, 최대 20000)
            page: 페이지 번호 (1~45)
            size: 한 페이지 결과 수 (1~15)
            sort: 정렬 기준 (accuracy | distance)

        Returns:
            KakaoSearchResponse
        """
        client = await self._get_client()

        params: dict[str, Any] = {
            "query": query,
            "page": page,
            "size": min(size, 15),  # 최대 15
            "sort": sort,
        }

        # 좌표 기반 검색 (선택적)
        if x is not None and y is not None:
            params["x"] = str(x)
            params["y"] = str(y)
            params["radius"] = min(radius, 20000)  # 최대 20km

        try:
            response = await client.get("/keyword.json", params=params)
            response.raise_for_status()
            data = response.json()

            result = self._parse_response(data, query)

            logger.info(
                "Kakao keyword search completed",
                extra={
                    "query": query,
                    "total_count": result.meta.total_count if result.meta else 0,
                    "result_count": len(result.places),
                    "has_location": x is not None,
                },
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(
                "Kakao API HTTP error",
                extra={
                    "status_code": e.response.status_code,
                    "query": query,
                    "detail": e.response.text[:200] if e.response.text else "",
                },
            )
            raise
        except httpx.TimeoutException as e:
            logger.error(
                "Kakao API timeout",
                extra={"query": query, "timeout": self._timeout},
            )
            raise
        except Exception as e:
            logger.error(
                "Kakao keyword search failed",
                extra={"query": query, "error": str(e)},
            )
            raise

    async def search_category(
        self,
        category_group_code: str,
        x: float,
        y: float,
        radius: int = 5000,
        page: int = 1,
        size: int = 15,
        sort: str = "distance",
    ) -> KakaoSearchResponse:
        """카테고리로 장소 검색.

        Args:
            category_group_code: 카테고리 그룹 코드 (MT1, CS2, CE7 등)
            x: 중심 좌표 경도 (필수)
            y: 중심 좌표 위도 (필수)
            radius: 검색 반경 (미터, 최대 20000)
            page: 페이지 번호 (1~45)
            size: 한 페이지 결과 수 (1~15)
            sort: 정렬 기준 (accuracy | distance)

        Returns:
            KakaoSearchResponse
        """
        client = await self._get_client()

        params = {
            "category_group_code": category_group_code,
            "x": str(x),
            "y": str(y),
            "radius": min(radius, 20000),
            "page": page,
            "size": min(size, 15),
            "sort": sort,
        }

        try:
            response = await client.get("/category.json", params=params)
            response.raise_for_status()
            data = response.json()

            query = f"category:{category_group_code}"
            result = self._parse_response(data, query)

            logger.info(
                "Kakao category search completed",
                extra={
                    "category": category_group_code,
                    "total_count": result.meta.total_count if result.meta else 0,
                    "result_count": len(result.places),
                    "x": x,
                    "y": y,
                },
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(
                "Kakao API HTTP error",
                extra={
                    "status_code": e.response.status_code,
                    "category": category_group_code,
                    "detail": e.response.text[:200] if e.response.text else "",
                },
            )
            raise
        except httpx.TimeoutException as e:
            logger.error(
                "Kakao API timeout",
                extra={"category": category_group_code, "timeout": self._timeout},
            )
            raise
        except Exception as e:
            logger.error(
                "Kakao category search failed",
                extra={"category": category_group_code, "error": str(e)},
            )
            raise

    def _parse_response(
        self,
        data: dict[str, Any],
        query: str,
    ) -> KakaoSearchResponse:
        """API 응답을 KakaoSearchResponse로 변환.

        Args:
            data: API 응답 JSON
            query: 검색 쿼리

        Returns:
            KakaoSearchResponse
        """
        meta_data = data.get("meta", {})
        documents = data.get("documents", [])

        places = [
            KakaoPlaceDTO(
                id=doc.get("id", ""),
                place_name=doc.get("place_name", ""),
                category_name=doc.get("category_name", ""),
                category_group_code=doc.get("category_group_code", ""),
                category_group_name=doc.get("category_group_name", ""),
                phone=doc.get("phone") or None,
                address_name=doc.get("address_name", ""),
                road_address_name=doc.get("road_address_name") or None,
                x=doc.get("x", "0"),
                y=doc.get("y", "0"),
                place_url=doc.get("place_url", ""),
                distance=doc.get("distance") or None,
            )
            for doc in documents
        ]

        meta = KakaoSearchMeta(
            total_count=meta_data.get("total_count", 0),
            pageable_count=meta_data.get("pageable_count", 0),
            is_end=meta_data.get("is_end", True),
            same_name=meta_data.get("same_name"),
        )

        return KakaoSearchResponse(
            places=places,
            meta=meta,
            query=query,
        )

    async def close(self) -> None:
        """HTTP 클라이언트 종료."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("Kakao Local HTTP client closed")


__all__ = ["KakaoLocalHttpClient"]
