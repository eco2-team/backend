"""Web Search Integrations.

웹 검색 구현체들:
- DuckDuckGo: 무료, API 키 불필요
- Tavily: LLM 최적화, 1000 req/월 무료
"""

from chat_worker.infrastructure.integrations.web_search.duckduckgo import (
    DuckDuckGoSearchClient,
)

__all__ = ["DuckDuckGoSearchClient"]
