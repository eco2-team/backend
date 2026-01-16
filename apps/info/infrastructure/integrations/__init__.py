"""External Integrations."""

from info.infrastructure.integrations.naver import NaverNewsClient
from info.infrastructure.integrations.newsdata import NewsDataClient

__all__ = ["NaverNewsClient", "NewsDataClient"]
