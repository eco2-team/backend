"""Tavily Search Client.

Tavily 웹 검색 구현체.
- LLM용으로 최적화된 검색 결과
- 1,000 req/월 무료
- API 키 필요

Dependencies:
    pip install tavily-python

Usage:
    client = TavilySearchClient(api_key="tvly-xxx")
    results = await client.search("분리배출 최신 정책")

환경변수:
    TAVILY_API_KEY: Tavily API 키
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Literal

from chat_worker.application.ports.web_search import (
    SearchResult,
    WebSearchPort,
    WebSearchResponse,
)

logger = logging.getLogger(__name__)


class TavilySearchClient(WebSearchPort):
    """Tavily 검색 클라이언트.

    LLM 에이전트를 위해 최적화된 검색 API.
    결과에 요약 및 관련성 점수 포함.
    """

    def __init__(self, api_key: str | None = None):
        """초기화.

        Args:
            api_key: Tavily API 키 (없으면 환경변수에서 로드)
        """
        self._api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not self._api_key:
            logger.warning("TAVILY_API_KEY not set, Tavily search will fail")

    async def search(
        self,
        query: str,
        max_results: int = 5,
        region: str = "kr-kr",
        time_range: Literal["day", "week", "month", "year", "all"] = "all",
    ) -> WebSearchResponse:
        """웹 검색 수행.

        Args:
            query: 검색어
            max_results: 최대 결과 수
            region: 지역 코드 (Tavily는 한정적 지원)
            time_range: 시간 범위 필터

        Returns:
            WebSearchResponse: 검색 결과
        """
        if not self._api_key:
            logger.error("Tavily API key not configured")
            return WebSearchResponse(
                query=query,
                results=[],
                total_results=0,
                search_engine="tavily",
            )

        try:
            results = await asyncio.to_thread(
                self._search_sync,
                query,
                max_results,
                time_range,
            )
            return results
        except Exception as e:
            logger.error(f"Tavily search failed: {e}")
            return WebSearchResponse(
                query=query,
                results=[],
                total_results=0,
                search_engine="tavily",
            )

    async def search_news(
        self,
        query: str,
        max_results: int = 5,
        region: str = "kr-kr",
    ) -> WebSearchResponse:
        """뉴스 검색 수행.

        Tavily는 별도 뉴스 API가 없으므로 일반 검색에 "news" 추가.

        Args:
            query: 검색어
            max_results: 최대 결과 수
            region: 지역 코드

        Returns:
            WebSearchResponse: 뉴스 검색 결과
        """
        news_query = f"{query} news latest"
        return await self.search(
            query=news_query,
            max_results=max_results,
            region=region,
            time_range="week",  # 뉴스는 최근 1주일로 제한
        )

    def _search_sync(
        self,
        query: str,
        max_results: int,
        time_range: str,
    ) -> WebSearchResponse:
        """동기 검색."""
        from tavily import TavilyClient

        client = TavilyClient(api_key=self._api_key)

        # time_range를 days로 변환
        days_map = {
            "day": 1,
            "week": 7,
            "month": 30,
            "year": 365,
            "all": None,
        }
        days = days_map.get(time_range)

        search_kwargs = {
            "query": query,
            "max_results": max_results,
            "search_depth": "advanced",  # 더 나은 결과
            "include_answer": False,  # 우리가 직접 답변 생성
            "include_raw_content": False,
        }

        if days:
            search_kwargs["days"] = days

        response = client.search(**search_kwargs)

        results = [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("content", ""),
                source=self._extract_source(r.get("url", "")),
            )
            for r in response.get("results", [])
        ]

        logger.info(f"Tavily search: query={query}, results={len(results)}")

        return WebSearchResponse(
            query=query,
            results=results,
            total_results=len(results),
            search_engine="tavily",
        )

    def _extract_source(self, url: str) -> str:
        """URL에서 소스 추출."""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            return parsed.netloc.replace("www.", "")
        except Exception:
            return ""
