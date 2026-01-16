"""Search Recyclable Price Command.

재활용자원 시세 검색 UseCase.

Clean Architecture:
- Command(UseCase): 이 파일 - Port 호출, 오케스트레이션
- Service: RecyclablePriceService - 순수 비즈니스 로직 (Port 의존 없음)
- Port: RecyclablePriceClientPort - 파일/캐시 기반
- Node(Adapter): recyclable_price_node.py - LangGraph glue
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from chat_worker.application.services.recyclable_price_service import (
    RecyclablePriceService,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.recyclable_price_client import (
        RecyclableCategory,
        RecyclablePriceClientPort,
        RecyclableRegion,
    )

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchRecyclablePriceInput:
    """Command 입력 DTO.

    Attributes:
        job_id: 작업 ID (로깅/추적용)
        item_name: 품목명 (예: "캔", "페트병")
        category: 카테고리 (선택, 카테고리 전체 조회 시)
        region: 권역 (선택)
        message: 원본 사용자 메시지 (품목명 추출용)
    """

    job_id: str
    item_name: str | None = None
    category: "RecyclableCategory | None" = None
    region: "RecyclableRegion | None" = None
    message: str = ""


@dataclass
class SearchRecyclablePriceOutput:
    """Command 출력 DTO.

    Attributes:
        success: 성공 여부
        price_context: 가격 정보 컨텍스트
        error_message: 에러 메시지
        events: 발생한 이벤트 목록
    """

    success: bool
    price_context: dict[str, Any] | None = None
    error_message: str | None = None
    events: list[str] = field(default_factory=list)


class SearchRecyclablePriceCommand:
    """재활용자원 시세 검색 Command (UseCase).

    Port 호출 + 오케스트레이션:
    1. 품목명 추출/검증 (Service - 순수 로직)
    2. 가격 조회 (RecyclablePriceClientPort)
    3. 컨텍스트 변환 (Service - 순수 로직)

    Usage:
        command = SearchRecyclablePriceCommand(price_client=client)
        output = await command.execute(input_dto)
    """

    def __init__(
        self,
        price_client: "RecyclablePriceClientPort",
    ) -> None:
        """초기화.

        Args:
            price_client: 재활용자원 가격 클라이언트 (Port)
        """
        self._price_client = price_client

    async def execute(
        self, input_dto: SearchRecyclablePriceInput
    ) -> SearchRecyclablePriceOutput:
        """Command 실행.

        Args:
            input_dto: 입력 DTO

        Returns:
            SearchRecyclablePriceOutput
        """
        events: list[str] = []

        # 1. 품목명 추출 (Service - 순수 로직)
        item_name = input_dto.item_name
        if not item_name and input_dto.message:
            item_name = RecyclablePriceService.extract_item_name_from_query(
                input_dto.message
            )
            if item_name:
                events.append("item_extracted_from_message")

        # 품목명 없으면 전체 조회 안내
        if not item_name and not input_dto.category:
            events.append("no_item_specified")
            return SearchRecyclablePriceOutput(
                success=True,
                price_context={
                    "type": "guide",
                    "message": (
                        "어떤 재활용품의 시세를 알려드릴까요?\n"
                        "예: 캔, 페트병, 신문지, 유리병 등"
                    ),
                },
                events=events,
            )

        # 2. 가격 조회 (Port)
        try:
            if input_dto.category:
                # 카테고리 전체 조회
                response = await self._price_client.get_category_prices(
                    category=input_dto.category,
                    region=input_dto.region,
                )
                events.append("category_prices_fetched")
            elif item_name is not None:
                # 품목명 검색
                response = await self._price_client.search_price(
                    item_name=item_name,
                    region=input_dto.region,
                )
                events.append("item_price_searched")
            else:
                # 이 경우는 위에서 이미 처리됨 (unreachable)
                raise ValueError("item_name or category required")

            logger.info(
                "Recyclable price search completed",
                extra={
                    "job_id": input_dto.job_id,
                    "item_name": item_name,
                    "category": input_dto.category.value if input_dto.category else None,
                    "count": response.total_count,
                },
            )

        except Exception as e:
            logger.error(
                "Recyclable price search failed",
                extra={
                    "job_id": input_dto.job_id,
                    "item_name": item_name,
                    "error": str(e),
                },
            )
            events.append("price_search_error")
            return SearchRecyclablePriceOutput(
                success=False,
                price_context=RecyclablePriceService.build_error_context(
                    "재활용자원 시세 조회에 실패했어요. 잠시 후 다시 시도해주세요."
                ),
                error_message=str(e),
                events=events,
            )

        # 3. 컨텍스트 변환 (Service - 순수 로직)
        if not response.has_results:
            events.append("no_results")
            return SearchRecyclablePriceOutput(
                success=True,
                price_context=RecyclablePriceService.build_not_found_context(
                    item_name or ""
                ),
                events=events,
            )

        events.append("results_found")
        context = RecyclablePriceService.format_search_results(response)

        return SearchRecyclablePriceOutput(
            success=True,
            price_context=context,
            events=events,
        )


__all__ = [
    "SearchRecyclablePriceCommand",
    "SearchRecyclablePriceInput",
    "SearchRecyclablePriceOutput",
]
