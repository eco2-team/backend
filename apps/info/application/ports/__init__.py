"""Application Ports (Interfaces)."""

from info.application.ports.news_cache import NewsCachePort
from info.application.ports.news_repository import (
    NewsCursor,
    NewsRepositoryPort,
    PaginatedResult,
)
from info.application.ports.news_source import NewsSourcePort
from info.application.ports.rate_limiter import (
    RateLimitConfig,
    RateLimiterPort,
    RateLimitStatus,
)

__all__ = [
    "NewsSourcePort",
    "NewsCachePort",
    "NewsRepositoryPort",
    "NewsCursor",
    "PaginatedResult",
    "RateLimiterPort",
    "RateLimitConfig",
    "RateLimitStatus",
]
