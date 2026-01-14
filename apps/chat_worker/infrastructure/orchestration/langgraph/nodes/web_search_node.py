"""Web Search Node - 웹 검색 서브에이전트.

사용자 질문에 대해 최신 웹 정보를 검색하는 노드.

사용 시나리오:
1. RAG에 없는 최신 분리배출 정책
2. 환경 관련 최신 뉴스/트렌드
3. 일반 상식 보완

Flow:
    Router → web_search → Answer
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.web_search import WebSearchPort

logger = logging.getLogger(__name__)


def create_web_search_node(
    web_search_client: "WebSearchPort",
    event_publisher: "ProgressNotifierPort",
):
    """웹 검색 노드 팩토리.

    Args:
        web_search_client: 웹 검색 클라이언트 (DuckDuckGo/Tavily)
        event_publisher: 이벤트 발행기

    Returns:
        web_search_node 함수
    """

    async def web_search_node(state: dict[str, Any]) -> dict[str, Any]:
        """웹 검색 노드.

        state에서 검색어를 추출하고 웹 검색을 수행.
        결과는 web_search_results로 state에 저장.
        """
        job_id = state["job_id"]
        message = state.get("message", "")
        intent = state.get("intent", "general")

        # 1. 이벤트: 시작
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="web_search",
            status="started",
            progress=40,
            message="🔍 웹에서 최신 정보를 검색 중...",
        )

        try:
            # 2. 검색어 최적화
            search_query = _optimize_search_query(message, intent)

            # 3. 웹 검색 수행
            if intent == "news" or "뉴스" in message or "최근" in message:
                # 뉴스 검색
                response = await web_search_client.search_news(
                    query=search_query,
                    max_results=5,
                    region="kr-kr",
                )
            else:
                # 일반 웹 검색
                response = await web_search_client.search(
                    query=search_query,
                    max_results=5,
                    region="kr-kr",
                    time_range="all",
                )

            # 4. 결과 포맷팅
            web_results = _format_results(response)

            logger.info(
                "Web search completed",
                extra={
                    "job_id": job_id,
                    "query": search_query,
                    "results_count": len(response.results),
                    "engine": response.search_engine,
                },
            )

            # 5. 이벤트: 완료
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="web_search",
                status="completed",
                progress=50,
                result={
                    "query": search_query,
                    "results_count": len(response.results),
                },
            )

            return {
                **state,
                "web_search_results": web_results,
                "web_search_query": search_query,
            }

        except Exception as e:
            logger.error(
                "Web search failed",
                extra={"job_id": job_id, "error": str(e)},
            )

            await event_publisher.notify_stage(
                task_id=job_id,
                stage="web_search",
                status="failed",
                result={"error": str(e)},
            )

            return {
                **state,
                "web_search_results": None,
                "web_search_error": str(e),
            }

    return web_search_node


def _optimize_search_query(message: str, intent: str) -> str:
    """검색어 최적화.

    사용자 질문을 검색에 적합한 형태로 변환.

    Args:
        message: 사용자 메시지
        intent: 감지된 인텐트

    Returns:
        최적화된 검색어
    """
    # 기본 검색어는 원본 메시지
    query = message.strip()

    # 분리배출 관련이면 키워드 추가
    if intent == "waste":
        if "정책" in query or "규정" in query:
            query = f"{query} 환경부 분리배출"
        elif "어떻게" in query:
            query = f"{query} 분리배출 방법"

    # 환경 관련 검색어 보강
    env_keywords = ["탄소", "재활용", "환경", "쓰레기", "폐기물"]
    if any(k in query for k in env_keywords):
        query = f"{query} 한국"

    return query


def _format_results(response) -> dict[str, Any]:
    """검색 결과 포맷팅.

    LLM이 이해하기 쉬운 형태로 변환.

    Args:
        response: WebSearchResponse

    Returns:
        포맷팅된 결과
    """
    if not response.results:
        return {
            "found": False,
            "message": "검색 결과가 없습니다.",
            "sources": [],
        }

    formatted_results = []
    for i, result in enumerate(response.results, 1):
        formatted_results.append({
            "index": i,
            "title": result.title,
            "snippet": result.snippet,
            "source": result.source,
            "url": result.url,
        })

    return {
        "found": True,
        "query": response.query,
        "engine": response.search_engine,
        "count": len(response.results),
        "results": formatted_results,
    }
