"""Web Search Service - 순수 비즈니스 로직.

Port 의존 없이 순수 로직만 담당:
- 검색어 최적화
- 결과 포맷팅
- 컨텍스트 변환

Port 호출(Web Search API)은 Command에서 담당.

Clean Architecture:
- Service: 이 파일 (순수 로직, Port 의존 없음)
- Command: SearchWebCommand (Port 호출, 오케스트레이션)
- Port: WebSearchPort (Web Search API 호출)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chat_worker.application.ports.web_search import WebSearchResponse

logger = logging.getLogger(__name__)


class WebSearchService:
    """웹 검색 비즈니스 로직 서비스 (순수 로직).

    Port 의존 없이 순수 비즈니스 로직만 담당:
    - 검색어 최적화
    - 결과 포맷팅
    - 컨텍스트 변환

    Web Search API 호출은 Command에서 담당.
    """

    @staticmethod
    def optimize_query(message: str, intent: str) -> str:
        """검색어 최적화.

        사용자 질문을 검색에 적합한 형태로 변환합니다.

        Args:
            message: 사용자 메시지
            intent: 감지된 인텐트

        Returns:
            최적화된 검색어
        """
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

    @staticmethod
    def should_search_news(message: str, intent: str) -> bool:
        """뉴스 검색 여부 판단.

        Args:
            message: 사용자 메시지
            intent: 감지된 인텐트

        Returns:
            뉴스 검색 필요 여부
        """
        news_keywords = ["뉴스", "최근", "최신", "소식", "발표"]
        return intent == "news" or any(kw in message for kw in news_keywords)

    @staticmethod
    def format_results(response: "WebSearchResponse") -> dict[str, Any]:
        """검색 결과 포맷팅.

        LLM이 이해하기 쉬운 형태로 변환합니다.

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
            formatted_results.append(
                {
                    "index": i,
                    "title": result.title,
                    "snippet": result.snippet,
                    "source": result.source,
                    "url": result.url,
                }
            )

        return {
            "found": True,
            "query": response.query,
            "engine": response.search_engine,
            "count": len(response.results),
            "results": formatted_results,
        }

    @staticmethod
    def to_answer_context(
        formatted_results: dict[str, Any],
        original_query: str,
    ) -> dict[str, Any]:
        """Answer 노드용 컨텍스트 생성.

        Args:
            formatted_results: 포맷팅된 검색 결과
            original_query: 원본 검색어

        Returns:
            Answer 노드용 컨텍스트
        """
        return {
            "web_search": formatted_results,
            "original_query": original_query,
            "has_web_results": formatted_results.get("found", False),
        }

    @staticmethod
    def build_error_context(error_message: str) -> dict[str, Any]:
        """에러 컨텍스트 생성.

        Args:
            error_message: 에러 메시지

        Returns:
            에러 컨텍스트
        """
        return {
            "found": False,
            "error": True,
            "message": error_message,
        }

    @staticmethod
    def extract_sources_for_citation(
        formatted_results: dict[str, Any],
    ) -> list[dict[str, str]]:
        """인용을 위한 출처 목록 추출.

        Args:
            formatted_results: 포맷팅된 검색 결과

        Returns:
            출처 목록 [{"title": ..., "url": ...}, ...]
        """
        if not formatted_results.get("found"):
            return []

        return [
            {"title": r["title"], "url": r["url"]}
            for r in formatted_results.get("results", [])
        ]
