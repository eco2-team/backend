"""DuckDuckGo Search Client.

DuckDuckGo 웹 검색 구현체.
- 무료
- API 키 불필요
- Rate limit 있음 (과도한 요청 시 차단)

Dependencies:
    pip install duckduckgo-search

Usage:
    client = DuckDuckGoSearchClient()
    results = await client.search("분리배출 최신 정책")
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

from chat_worker.application.ports.web_search import (
    SearchResult,
    WebSearchPort,
    WebSearchResponse,
)

logger = logging.getLogger(__name__)


class DuckDuckGoSearchClient(WebSearchPort):
    """DuckDuckGo 검색 클라이언트.

    duckduckgo-search 패키지를 사용한 웹 검색 구현.
    비동기 컨텍스트에서 동기 API를 thread pool로 실행.
    """

    def __init__(self, timeout: int = 10):
        """초기화.

        Args:
            timeout: 검색 타임아웃 (초)
        """
        self._timeout = timeout

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
            region: 지역 코드
            time_range: 시간 범위 필터

        Returns:
            WebSearchResponse: 검색 결과
        """
        try:
            # 동기 함수를 thread pool에서 실행
            results = await asyncio.to_thread(
                self._search_sync,
                query,
                max_results,
                region,
                time_range,
            )
            return results
        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            return WebSearchResponse(
                query=query,
                results=[],
                total_results=0,
                search_engine="duckduckgo",
            )

    async def search_news(
        self,
        query: str,
        max_results: int = 5,
        region: str = "kr-kr",
    ) -> WebSearchResponse:
        """뉴스 검색 수행.

        Args:
            query: 검색어
            max_results: 최대 결과 수
            region: 지역 코드

        Returns:
            WebSearchResponse: 뉴스 검색 결과
        """
        try:
            results = await asyncio.to_thread(
                self._search_news_sync,
                query,
                max_results,
                region,
            )
            return results
        except Exception as e:
            logger.error(f"DuckDuckGo news search failed: {e}")
            return WebSearchResponse(
                query=query,
                results=[],
                total_results=0,
                search_engine="duckduckgo",
            )

    def _search_sync(
        self,
        query: str,
        max_results: int,
        region: str,
        time_range: str,
    ) -> WebSearchResponse:
        """동기 웹 검색."""
        from duckduckgo_search import DDGS

        # time_range 매핑
        timelimit_map = {
            "day": "d",
            "week": "w",
            "month": "m",
            "year": "y",
            "all": None,
        }
        timelimit = timelimit_map.get(time_range)

        with DDGS() as ddgs:
            raw_results = list(
                ddgs.text(
                    query,
                    region=region,
                    timelimit=timelimit,
                    max_results=max_results,
                )
            )

        results = [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("href", ""),
                snippet=r.get("body", ""),
                source=self._extract_source(r.get("href", "")),
            )
            for r in raw_results
        ]

        logger.info(f"DuckDuckGo search: query={query}, results={len(results)}")

        return WebSearchResponse(
            query=query,
            results=results,
            total_results=len(results),
            search_engine="duckduckgo",
        )

    def _search_news_sync(
        self,
        query: str,
        max_results: int,
        region: str,
    ) -> WebSearchResponse:
        """동기 뉴스 검색."""
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            raw_results = list(
                ddgs.news(
                    query,
                    region=region,
                    max_results=max_results,
                )
            )

        results = [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("body", ""),
                source=r.get("source", ""),
            )
            for r in raw_results
        ]

        logger.info(f"DuckDuckGo news search: query={query}, results={len(results)}")

        return WebSearchResponse(
            query=query,
            results=results,
            total_results=len(results),
            search_engine="duckduckgo",
        )

    def _extract_source(self, url: str) -> str:
        """URL에서 소스 추출.

        Args:
            url: URL

        Returns:
            도메인 이름
        """
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            return parsed.netloc.replace("www.", "")
        except Exception:
            return ""
