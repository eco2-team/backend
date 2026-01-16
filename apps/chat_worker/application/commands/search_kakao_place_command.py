"""Search Kakao Place Command.

카카오 로컬 API 장소 검색 UseCase.

Clean Architecture:
- Command(UseCase): 이 파일 - Port 호출, 오케스트레이션
- Service: KakaoPlaceService - 순수 비즈니스 로직 (Port 의존 없음)
- Port: KakaoLocalClientPort - HTTP API 호출
- Node(Adapter): kakao_place_node.py - LangGraph glue
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from chat_worker.application.services.kakao_place_service import KakaoPlaceService

if TYPE_CHECKING:
    from chat_worker.application.ports.kakao_local_client import KakaoLocalClientPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchKakaoPlaceInput:
    """Command 입력 DTO.

    Attributes:
        job_id: 작업 ID (로깅/추적용)
        query: 검색 키워드
        user_location: 사용자 위치 (lat, lon 딕셔너리)
        search_type: 검색 타입 (keyword | category)
        category_code: 카테고리 검색 시 코드 (예: PO3, CE7)
        radius: 검색 반경 (미터)
        limit: 최대 결과 수
    """

    job_id: str
    query: str = ""
    user_location: dict[str, Any] | None = None
    search_type: str = "keyword"  # keyword | category
    category_code: str | None = None
    radius: int = 5000
    limit: int = 10


@dataclass
class SearchKakaoPlaceOutput:
    """Command 출력 DTO.

    Attributes:
        success: 성공 여부
        places_context: 장소 검색 결과 컨텍스트
        needs_location: 위치 정보 필요 여부 (HITL 트리거)
        error_message: 에러 메시지
        events: 발생한 이벤트 목록
    """

    success: bool
    places_context: dict[str, Any] | None = None
    needs_location: bool = False
    error_message: str | None = None
    events: list[str] = field(default_factory=list)


class SearchKakaoPlaceCommand:
    """카카오 장소 검색 Command (UseCase).

    Port 호출 + 오케스트레이션:
    1. 검색어/위치 검증 (Service - 순수 로직)
    2. API 호출 (KakaoLocalClientPort)
    3. 컨텍스트 변환 (Service - 순수 로직)

    Usage:
        command = SearchKakaoPlaceCommand(kakao_client=client)
        output = await command.execute(input_dto)
    """

    def __init__(
        self,
        kakao_client: "KakaoLocalClientPort",
    ) -> None:
        """초기화.

        Args:
            kakao_client: 카카오 로컬 클라이언트 (Port)
        """
        self._kakao_client = kakao_client

    async def execute(self, input_dto: SearchKakaoPlaceInput) -> SearchKakaoPlaceOutput:
        """Command 실행.

        Args:
            input_dto: 입력 DTO

        Returns:
            SearchKakaoPlaceOutput
        """
        events: list[str] = []

        # 1. 검색어 검증 (키워드 검색 시)
        if not input_dto.query and input_dto.search_type == "keyword":
            return SearchKakaoPlaceOutput(
                success=False,
                error_message="검색어가 필요해요.",
                events=["query_missing"],
            )

        # 2. 위치 추출 (Service - 순수 로직)
        lat, lon = KakaoPlaceService.extract_coordinates(input_dto.user_location)

        # 카테고리 검색은 위치 필수
        if input_dto.search_type == "category":
            if not KakaoPlaceService.validate_coordinates(lat, lon):
                events.append("location_required_for_category")
                return SearchKakaoPlaceOutput(
                    success=True,
                    places_context=KakaoPlaceService.build_no_location_context(),
                    needs_location=True,
                    events=events,
                )

        # 3. API 호출 (Port)
        try:
            if input_dto.search_type == "category" and input_dto.category_code:
                # 카테고리 검색
                response = await self._kakao_client.search_category(
                    category_group_code=input_dto.category_code,
                    x=lon,  # 경도
                    y=lat,  # 위도
                    radius=input_dto.radius,
                    size=min(input_dto.limit, 15),
                )
                events.append("category_search_called")
            else:
                # 키워드 검색
                # 위치가 있으면 거리순, 없으면 정확도순
                sort = "distance" if lat and lon else "accuracy"
                response = await self._kakao_client.search_keyword(
                    query=input_dto.query,
                    x=lon if lon else None,
                    y=lat if lat else None,
                    radius=input_dto.radius,
                    size=min(input_dto.limit, 15),
                    sort=sort,
                )
                events.append("keyword_search_called")

            logger.info(
                "Kakao search completed",
                extra={
                    "job_id": input_dto.job_id,
                    "query": input_dto.query,
                    "search_type": input_dto.search_type,
                    "count": len(response.places),
                },
            )

        except Exception as e:
            logger.error(
                "Kakao search failed",
                extra={
                    "job_id": input_dto.job_id,
                    "query": input_dto.query,
                    "error": str(e),
                },
            )
            events.append("kakao_api_error")
            return SearchKakaoPlaceOutput(
                success=False,
                places_context=KakaoPlaceService.build_error_context(
                    "장소 검색에 실패했어요. 잠시 후 다시 시도해주세요."
                ),
                error_message=str(e),
                events=events,
            )

        # 4. 컨텍스트 변환 (Service - 순수 로직)
        if not response.places:
            events.append("no_results")
            context = KakaoPlaceService.build_not_found_context(input_dto.query)
        else:
            events.append("results_found")
            context = KakaoPlaceService.to_answer_context(
                places=response.places,
                query=input_dto.query,
                meta=response.meta,
            )

        return SearchKakaoPlaceOutput(
            success=True,
            places_context=context,
            events=events,
        )


__all__ = [
    "SearchKakaoPlaceCommand",
    "SearchKakaoPlaceInput",
    "SearchKakaoPlaceOutput",
]
