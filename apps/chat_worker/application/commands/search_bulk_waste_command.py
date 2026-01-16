"""Search Bulk Waste Command.

대형폐기물 정보 검색 UseCase.

Clean Architecture:
- Command(UseCase): 이 파일 - Port 호출, 오케스트레이션
- Service: BulkWasteService - 순수 비즈니스 로직 (Port 의존 없음)
- Port: BulkWasteClientPort - HTTP API 호출
- Node(Adapter): bulk_waste_node.py - LangGraph glue
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from chat_worker.application.services.bulk_waste_service import BulkWasteService

if TYPE_CHECKING:
    from chat_worker.application.ports.bulk_waste_client import BulkWasteClientPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchBulkWasteInput:
    """Command 입력 DTO.

    Attributes:
        job_id: 작업 ID (로깅/추적용)
        sigungu: 시군구명 (예: "강남구")
        item_name: 품목명 (예: "소파", "냉장고") - 수수료 조회용
        user_location: 사용자 위치 (sigungu 없을 때 추출용)
        search_type: 검색 타입 (collection | fee | all)
    """

    job_id: str
    sigungu: str | None = None
    item_name: str | None = None
    user_location: dict[str, Any] | None = None
    search_type: str = "all"  # collection | fee | all


@dataclass
class SearchBulkWasteOutput:
    """Command 출력 DTO.

    Attributes:
        success: 성공 여부
        bulk_waste_context: 대형폐기물 정보 컨텍스트
        needs_location: 위치 정보 필요 여부 (HITL 트리거)
        error_message: 에러 메시지
        events: 발생한 이벤트 목록
    """

    success: bool
    bulk_waste_context: dict[str, Any] | None = None
    needs_location: bool = False
    error_message: str | None = None
    events: list[str] = field(default_factory=list)


class SearchBulkWasteCommand:
    """대형폐기물 정보 검색 Command (UseCase).

    Port 호출 + 오케스트레이션:
    1. 시군구 추출/검증 (Service - 순수 로직)
    2. API 호출 (BulkWasteClientPort)
    3. 컨텍스트 변환 (Service - 순수 로직)

    Usage:
        command = SearchBulkWasteCommand(bulk_waste_client=client)
        output = await command.execute(input_dto)
    """

    def __init__(
        self,
        bulk_waste_client: "BulkWasteClientPort",
    ) -> None:
        """초기화.

        Args:
            bulk_waste_client: 대형폐기물 클라이언트 (Port)
        """
        self._bulk_waste_client = bulk_waste_client

    async def execute(self, input_dto: SearchBulkWasteInput) -> SearchBulkWasteOutput:
        """Command 실행.

        Args:
            input_dto: 입력 DTO

        Returns:
            SearchBulkWasteOutput
        """
        events: list[str] = []

        # 1. 시군구 추출 (Service - 순수 로직)
        sigungu = input_dto.sigungu
        if not sigungu:
            sigungu = BulkWasteService.extract_sigungu(input_dto.user_location)

        # 시군구 없으면 HITL 트리거
        if not sigungu:
            events.append("location_required")
            return SearchBulkWasteOutput(
                success=True,
                bulk_waste_context=BulkWasteService.build_no_location_context(),
                needs_location=True,
                events=events,
            )

        # 2. API 호출 (Port)
        try:
            collection_info = None
            fee_items = None
            disposal_info = None

            # 수거 정보 조회
            if input_dto.search_type in ("collection", "all"):
                collection_info = await self._bulk_waste_client.get_bulk_waste_info(
                    sigungu=sigungu,
                )
                events.append("collection_info_fetched")

                # 행정안전부 API로 배출 방법 추가 조회
                disposal_response = await self._bulk_waste_client.search_disposal_info(
                    sigungu=sigungu,
                    page_size=5,
                )
                disposal_info = disposal_response.results
                events.append("disposal_info_fetched")

            # 수수료 조회 (품목명이 있을 때)
            if input_dto.search_type in ("fee", "all") and input_dto.item_name:
                fee_items = await self._bulk_waste_client.search_bulk_waste_fee(
                    sigungu=sigungu,
                    item_name=input_dto.item_name,
                )
                events.append("fee_info_fetched")

            logger.info(
                "Bulk waste search completed",
                extra={
                    "job_id": input_dto.job_id,
                    "sigungu": sigungu,
                    "item_name": input_dto.item_name,
                    "search_type": input_dto.search_type,
                    "has_collection": collection_info is not None,
                    "has_fees": bool(fee_items),
                    "disposal_count": len(disposal_info) if disposal_info else 0,
                },
            )

        except Exception as e:
            logger.error(
                "Bulk waste search failed",
                extra={
                    "job_id": input_dto.job_id,
                    "sigungu": sigungu,
                    "error": str(e),
                },
            )
            events.append("bulk_waste_api_error")
            return SearchBulkWasteOutput(
                success=False,
                bulk_waste_context=BulkWasteService.build_error_context(
                    "대형폐기물 정보 조회에 실패했어요. 잠시 후 다시 시도해주세요."
                ),
                error_message=str(e),
                events=events,
            )

        # 3. 컨텍스트 변환 (Service - 순수 로직)
        # 정보가 없는 경우
        if not collection_info and not fee_items and not disposal_info:
            events.append("no_results")
            return SearchBulkWasteOutput(
                success=True,
                bulk_waste_context=BulkWasteService.build_not_found_context(sigungu),
                events=events,
            )

        # 통합 컨텍스트 생성
        events.append("results_found")
        context = BulkWasteService.to_answer_context(
            disposal_info=disposal_info,
            collection_info=collection_info,
            fee_items=fee_items,
            sigungu=sigungu,
        )

        return SearchBulkWasteOutput(
            success=True,
            bulk_waste_context=context,
            events=events,
        )


__all__ = [
    "SearchBulkWasteCommand",
    "SearchBulkWasteInput",
    "SearchBulkWasteOutput",
]
