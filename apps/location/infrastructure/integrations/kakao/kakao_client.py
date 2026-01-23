"""카카오 로컬 HTTP 클라이언트.

카카오 로컬 API의 HTTP 구현체.
- 키워드 검색: GET /v2/local/search/keyword.json
- 인증: Authorization: KakaoAK {REST_API_KEY}
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from location.application.ports.kakao_local_client import (
    KakaoLocalClientPort,
    KakaoPlaceDTO,
    KakaoSearchMeta,
    KakaoSearchResponse,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10.0


class KakaoLocalHttpClient(KakaoLocalClientPort):
    """카카오 로컬 HTTP 클라이언트."""

    BASE_URL = "https://dapi.kakao.com/v2/local/search"

    def __init__(self, api_key: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            async with self._lock:
                if self._client is None:
                    self._client = httpx.AsyncClient(
                        base_url=self.BASE_URL,
                        headers={"Authorization": f"KakaoAK {self._api_key}"},
                        timeout=self._timeout,
                    )
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
        """키워드로 장소 검색."""
        client = await self._get_client()

        params: dict[str, Any] = {
            "query": query,
            "page": page,
            "size": min(size, 15),
            "sort": sort,
        }

        if x is not None and y is not None:
            params["x"] = str(x)
            params["y"] = str(y)
            params["radius"] = min(radius, 20000)

        try:
            response = await client.get("/keyword.json", params=params)
            response.raise_for_status()
            data = response.json()
            return self._parse_response(data, query)
        except httpx.HTTPStatusError as e:
            logger.error(
                "Kakao API HTTP error",
                extra={"status_code": e.response.status_code, "query": query},
            )
            raise
        except httpx.TimeoutException:
            logger.error("Kakao API timeout", extra={"query": query})
            raise
        except Exception as e:
            logger.error("Kakao keyword search failed", extra={"query": query, "error": str(e)})
            raise

    def _parse_response(self, data: dict[str, Any], query: str) -> KakaoSearchResponse:
        meta_data = data.get("meta", {})
        documents = data.get("documents", [])

        places = []
        for doc in documents:
            x = doc.get("x")
            y = doc.get("y")
            if not x or not y:
                continue
            places.append(
                KakaoPlaceDTO(
                    id=doc.get("id", ""),
                    place_name=doc.get("place_name", ""),
                    category_name=doc.get("category_name", ""),
                    category_group_code=doc.get("category_group_code", ""),
                    category_group_name=doc.get("category_group_name", ""),
                    phone=doc.get("phone") or None,
                    address_name=doc.get("address_name", ""),
                    road_address_name=doc.get("road_address_name") or None,
                    x=x,
                    y=y,
                    place_url=doc.get("place_url", ""),
                    distance=doc.get("distance") or None,
                )
            )

        meta = KakaoSearchMeta(
            total_count=meta_data.get("total_count", 0),
            pageable_count=meta_data.get("pageable_count", 0),
            is_end=meta_data.get("is_end", True),
            same_name=meta_data.get("same_name"),
        )

        return KakaoSearchResponse(places=places, meta=meta, query=query)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
