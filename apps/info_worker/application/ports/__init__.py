"""Application ports (Abstractions)."""

from info_worker.application.ports.news_repository import NewsRepositoryPort
from info_worker.application.ports.news_cache import NewsCachePort
from info_worker.application.ports.news_source import NewsSourcePort

__all__ = ["NewsRepositoryPort", "NewsCachePort", "NewsSourcePort"]
