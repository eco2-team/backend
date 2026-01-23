"""Suggest Places Query.

자동완성을 위한 장소 제안 Query.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from location.application.nearby.dto import SuggestEntryDTO

if TYPE_CHECKING:
    from location.application.ports.kakao_local_client import KakaoLocalClientPort

logger = logging.getLogger(__name__)

MAX_SUGGEST_RESULTS = 5


class SuggestPlacesQuery:
    """장소 자동완성 제안 Query.

    Kakao API keyword search로 장소 후보를 반환합니다.
    """

    def __init__(self, kakao_client: "KakaoLocalClientPort") -> None:
        self._kakao = kakao_client

    async def execute(self, query: str) -> list[SuggestEntryDTO]:
        """검색어에 대한 장소 제안을 반환합니다.

        Args:
            query: 검색어

        Returns:
            SuggestEntryDTO 목록 (최대 5개)
        """
        response = await self._kakao.search_keyword(
            query=query,
            size=MAX_SUGGEST_RESULTS,
            sort="accuracy",
        )

        results: list[SuggestEntryDTO] = []
        for place in response.places:
            results.append(
                SuggestEntryDTO(
                    place_name=place.place_name,
                    address=place.road_address_name or place.address_name,
                    latitude=place.latitude,
                    longitude=place.longitude,
                    place_url=place.place_url or None,
                )
            )

        logger.info(
            "Suggest query completed",
            extra={"query": query, "results_count": len(results)},
        )
        return results
