"""Search Collection Point Command.

수거함 위치 검색 UseCase.

Clean Architecture:
- Command(UseCase): 이 파일 - Port 호출, 오케스트레이션
- Port: CollectionPointClientPort - HTTP API 호출
- Node(Adapter): collection_point_node.py - LangGraph glue

사용 시나리오:
1. "폐휴대폰 어디서 버려?" → 근처 수거함 위치 안내
2. "폐건전지 수거함" → 수거함 검색
3. 특정 지역 수거함 검색 (예: "강남구 폐가전 수거함")

데이터 소스:
- 한국환경공단 폐전자제품 수거함 (KECO API)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chat_worker.application.ports.collection_point_client import (
        CollectionPointClientPort,
    )

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchCollectionPointInput:
    """Command 입력 DTO.

    Attributes:
        job_id: 작업 ID (로깅/추적용)
        address_keyword: 주소 검색어 (예: "강남구", "용산")
        name_keyword: 상호명 검색어 (예: "이마트", "주민센터")
        user_location: 사용자 위치 (주소 추출용)
        limit: 최대 결과 수
    """

    job_id: str
    address_keyword: str | None = None
    name_keyword: str | None = None
    user_location: dict[str, Any] | None = None
    limit: int = 5


@dataclass
class SearchCollectionPointOutput:
    """Command 출력 DTO.

    Attributes:
        success: 성공 여부
        collection_point_context: 수거함 컨텍스트 (answer에 주입)
        needs_location: 위치 정보 필요 여부
        error_message: 에러 메시지
        events: 발생한 이벤트 목록
    """

    success: bool
    collection_point_context: dict[str, Any] | None = None
    needs_location: bool = False
    error_message: str | None = None
    events: list[str] = field(default_factory=list)


class SearchCollectionPointCommand:
    """수거함 위치 검색 Command (UseCase).

    Port 호출 + 오케스트레이션:
    1. 검색 조건 추출/검증
    2. API 호출 (CollectionPointClientPort)
    3. 컨텍스트 변환

    Usage:
        command = SearchCollectionPointCommand(client=client)
        output = await command.execute(input_dto)
    """

    def __init__(
        self,
        collection_point_client: "CollectionPointClientPort",
    ) -> None:
        """초기화.

        Args:
            collection_point_client: 수거함 클라이언트 (Port)
        """
        self._client = collection_point_client

    async def execute(
        self, input_dto: SearchCollectionPointInput
    ) -> SearchCollectionPointOutput:
        """Command 실행.

        Args:
            input_dto: 입력 DTO

        Returns:
            SearchCollectionPointOutput
        """
        events: list[str] = []

        # 1. 검색 조건 추출
        address_keyword = input_dto.address_keyword
        name_keyword = input_dto.name_keyword

        # user_location에서 주소 추출 (address_keyword 없을 때)
        if not address_keyword and input_dto.user_location:
            address_keyword = self._extract_address(input_dto.user_location)
            if address_keyword:
                events.append("address_extracted_from_location")

        # 검색 조건 없으면 가이드 응답
        if not address_keyword and not name_keyword:
            events.append("no_search_criteria")
            return SearchCollectionPointOutput(
                success=True,
                collection_point_context=self._build_guide_context(),
                needs_location=True,
                events=events,
            )

        # 2. API 호출 (Port)
        try:
            response = await self._client.search_collection_points(
                address_keyword=address_keyword,
                name_keyword=name_keyword,
                page=1,
                page_size=input_dto.limit,
            )
            events.append("api_called")

            logger.info(
                "Collection point search completed",
                extra={
                    "job_id": input_dto.job_id,
                    "address_keyword": address_keyword,
                    "name_keyword": name_keyword,
                    "total_count": response.total_count,
                    "result_count": len(response.results),
                },
            )

        except Exception as e:
            logger.error(
                "Collection point search failed",
                extra={
                    "job_id": input_dto.job_id,
                    "error": str(e),
                },
            )
            events.append("api_error")
            return SearchCollectionPointOutput(
                success=False,
                collection_point_context=self._build_error_context(),
                error_message=str(e),
                events=events,
            )

        # 3. 컨텍스트 변환
        if not response.results:
            events.append("no_results")
            return SearchCollectionPointOutput(
                success=True,
                collection_point_context=self._build_not_found_context(
                    address_keyword, name_keyword
                ),
                events=events,
            )

        events.append("results_found")
        context = self._build_result_context(
            results=response.results,
            total_count=response.total_count,
            address_keyword=address_keyword,
            name_keyword=name_keyword,
        )

        return SearchCollectionPointOutput(
            success=True,
            collection_point_context=context,
            events=events,
        )

    def _extract_address(self, user_location: dict[str, Any]) -> str | None:
        """user_location에서 주소 추출.

        구/동 단위 추출 우선.
        """
        # 구조화된 주소 필드 우선
        if "gu" in user_location:
            return user_location["gu"]
        if "district" in user_location:
            return user_location["district"]

        # 전체 주소에서 추출
        address = user_location.get("address", "")
        if not address:
            return None

        # 서울특별시 강남구 → 강남구 추출
        import re

        match = re.search(r"([가-힣]+[구군시])", address)
        if match:
            return match.group(1)

        return None

    def _build_guide_context(self) -> dict[str, Any]:
        """검색 가이드 컨텍스트."""
        return {
            "type": "guide",
            "found": False,
            "count": 0,
            "context": (
                "폐전자제품 수거함 위치를 찾으려면 지역 정보가 필요해요. "
                "어느 지역(구)에서 찾으시나요?"
            ),
            "items": [],
        }

    def _build_not_found_context(
        self,
        address_keyword: str | None,
        name_keyword: str | None,
    ) -> dict[str, Any]:
        """결과 없음 컨텍스트."""
        search_term = address_keyword or name_keyword or ""
        return {
            "type": "not_found",
            "found": False,
            "count": 0,
            "context": f"'{search_term}' 근처에서 수거함을 찾지 못했어요.",
            "items": [],
            "search_keyword": search_term,
        }

    def _build_error_context(self) -> dict[str, Any]:
        """에러 컨텍스트."""
        return {
            "type": "error",
            "found": False,
            "count": 0,
            "context": "수거함 정보 조회 중 오류가 발생했어요. 잠시 후 다시 시도해주세요.",
            "items": [],
        }

    def _build_result_context(
        self,
        results: list,
        total_count: int,
        address_keyword: str | None,
        name_keyword: str | None,
    ) -> dict[str, Any]:
        """검색 결과 컨텍스트."""
        items = []
        for point in results:
            items.append({
                "name": point.name,
                "address": point.address,
                "collection_types": point.collection_types_text,
                "is_free": point.is_free,
                "place_category": point.place_category,
            })

        # Answer에 주입할 컨텍스트 문자열 생성
        context_lines = [
            f"🗑️ '{address_keyword or name_keyword}' 근처 폐전자제품 수거함 "
            f"({len(results)}곳 / 총 {total_count}곳):"
        ]
        for i, item in enumerate(items[:3], 1):
            free_text = "무료" if item["is_free"] else "유료"
            context_lines.append(
                f"{i}. {item['name']} ({item['place_category'] or '기타'}, {free_text})"
            )
            context_lines.append(f"   📍 {item['address']}")
            context_lines.append(f"   수거: {item['collection_types']}")

        if len(results) > 3:
            context_lines.append(f"... 외 {len(results) - 3}곳 더 있어요.")

        return {
            "type": "results",
            "found": True,
            "count": len(results),
            "total_count": total_count,
            "context": "\n".join(context_lines),
            "items": items,
            "search_keyword": address_keyword or name_keyword,
        }


__all__ = [
    "SearchCollectionPointCommand",
    "SearchCollectionPointInput",
    "SearchCollectionPointOutput",
]
