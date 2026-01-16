"""Search Web Command.

웹 검색 UseCase.

Clean Architecture:
- Command(UseCase): 이 파일 - Port 호출, 오케스트레이션
- Service: WebSearchService - 순수 비즈니스 로직 (검색어 최적화, 결과 포맷팅)
- Port: WebSearchPort - Web Search API 호출
- Node(Adapter): web_search_node.py - LangGraph glue

구조:
- Command: 검색 타입 판단, API 호출, Service 호출, 오케스트레이션
- Service: 검색어 최적화, 결과 포맷팅 (Port 의존 없음)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from chat_worker.application.services.web_search_service import WebSearchService

if TYPE_CHECKING:
    from chat_worker.application.ports.web_search import WebSearchPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchWebInput:
    """Command 입력 DTO."""

    job_id: str
    message: str
    intent: str = "general"
    max_results: int = 5
    region: str = "kr-kr"


@dataclass
class SearchWebOutput:
    """Command 출력 DTO."""

    success: bool
    web_search_results: dict[str, Any] | None = None
    search_query: str | None = None  # 실제 사용된 검색어
    error_message: str | None = None
    events: list[str] = field(default_factory=list)


class SearchWebCommand:
    """웹 검색 Command (UseCase).

    Port 호출 + 오케스트레이션:
    1. 검색어 최적화 (Service - 순수 로직)
    2. 검색 타입 판단 (Service - 순수 로직)
    3. Web Search API 호출 (WebSearchPort)
    4. 결과 포맷팅 (Service - 순수 로직)

    Port 주입:
    - web_search_client: 웹 검색 API 클라이언트
    """

    def __init__(
        self,
        web_search_client: "WebSearchPort",
    ) -> None:
        """Command 초기화.

        Args:
            web_search_client: 웹 검색 클라이언트
        """
        self._web_search_client = web_search_client

    async def execute(self, input_dto: SearchWebInput) -> SearchWebOutput:
        """Command 실행.

        Args:
            input_dto: 입력 DTO

        Returns:
            출력 DTO
        """
        events: list[str] = []

        # 1. 검색어 최적화 (Service - 순수 로직)
        search_query = WebSearchService.optimize_query(
            message=input_dto.message,
            intent=input_dto.intent,
        )
        events.append("query_optimized")

        # 2. 검색 타입 판단 (Service - 순수 로직)
        is_news_search = WebSearchService.should_search_news(
            message=input_dto.message,
            intent=input_dto.intent,
        )

        # 3. Web Search API 호출 (Command에서 Port 호출)
        try:
            if is_news_search:
                response = await self._web_search_client.search_news(
                    query=search_query,
                    max_results=input_dto.max_results,
                    region=input_dto.region,
                )
                events.append("news_search_called")
            else:
                response = await self._web_search_client.search(
                    query=search_query,
                    max_results=input_dto.max_results,
                    region=input_dto.region,
                    time_range="all",
                )
                events.append("web_search_called")

            logger.info(
                "Web search completed",
                extra={
                    "job_id": input_dto.job_id,
                    "query": search_query,
                    "is_news": is_news_search,
                    "results_count": len(response.results),
                    "engine": response.search_engine,
                },
            )

        except Exception as e:
            logger.error(
                "Web search failed",
                extra={"job_id": input_dto.job_id, "error": str(e)},
            )
            events.append("web_search_error")
            return SearchWebOutput(
                success=False,
                web_search_results=WebSearchService.build_error_context(str(e)),
                search_query=search_query,
                error_message="웹 검색에 실패했어요.",
                events=events,
            )

        # 4. 결과 포맷팅 (Service - 순수 로직)
        formatted_results = WebSearchService.format_results(response)
        events.append("results_formatted")

        # 5. Answer 컨텍스트 생성 (Service - 순수 로직)
        context = WebSearchService.to_answer_context(
            formatted_results=formatted_results,
            original_query=input_dto.message,
        )

        return SearchWebOutput(
            success=True,
            web_search_results=context,
            search_query=search_query,
            events=events,
        )
