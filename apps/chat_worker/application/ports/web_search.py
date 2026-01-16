"""Web Search Port - 웹 검색 추상화.

웹 검색 기능의 Port(인터페이스) 정의.
DuckDuckGo, Tavily 등 다양한 검색 엔진 구현체로 교체 가능.

Clean Architecture:
- Port: 이 파일 (인터페이스)
- Adapter: infrastructure/integrations/web_search/ (구현체)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class SearchResult:
    """검색 결과 단일 항목."""

    title: str
    url: str
    snippet: str
    source: str = ""  # 출처 (예: wikipedia, news)


@dataclass
class WebSearchResponse:
    """웹 검색 응답."""

    query: str
    results: list[SearchResult] = field(default_factory=list)
    total_results: int = 0
    search_engine: str = ""  # 사용된 검색 엔진


class WebSearchPort(ABC):
    """웹 검색 Port (추상 인터페이스).

    다양한 검색 엔진 구현체로 교체 가능:
    - DuckDuckGo (무료, API 키 불필요)
    - Tavily (LLM 최적화, 1000 req/월 무료)
    - Serper (Google 결과, 2500 req/월 무료)
    """

    @abstractmethod
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
            region: 지역 코드 (예: kr-kr, en-us)
            time_range: 시간 범위 필터

        Returns:
            WebSearchResponse: 검색 결과
        """
        pass

    @abstractmethod
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
        pass
