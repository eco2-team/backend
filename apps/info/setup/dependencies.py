"""Dependency Injection.

FastAPI 의존성 주입 팩토리.
"""

from __future__ import annotations

from typing import AsyncGenerator

import httpx
from redis.asyncio import Redis

from info.application.commands.fetch_news_command import FetchNewsCommand
from info.application.ports.news_source import NewsSourcePort
from info.application.ports.rate_limiter import RateLimitConfig
from info.application.services.news_aggregator import NewsAggregatorService
from info.infrastructure.cache.redis_news_cache import RedisNewsCache
from info.infrastructure.cache.redis_rate_limiter import RedisRateLimiter
from info.infrastructure.integrations.naver.naver_news_client import NaverNewsClient
from info.infrastructure.integrations.newsdata.newsdata_client import NewsDataClient
from info.infrastructure.integrations.og.og_image_extractor import OGImageExtractor
from info.setup.config import get_settings

# Rate Limit 설정 (일일 호출 제한)
RATE_LIMIT_CONFIGS = {
    "naver": RateLimitConfig(source="naver", daily_limit=25000),
    "newsdata": RateLimitConfig(source="newsdata", daily_limit=200),
}


async def get_fetch_news_command() -> AsyncGenerator[FetchNewsCommand, None]:
    """FetchNewsCommand 의존성 주입.

    FastAPI Depends에서 사용.
    """
    settings = get_settings()

    # HTTP Client
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        # Redis
        redis = Redis.from_url(settings.redis_url, decode_responses=True)

        try:
            # Cache
            cache = RedisNewsCache(redis=redis, ttl=settings.news_cache_ttl)

            # Rate Limiter
            rate_limiter = RedisRateLimiter(redis=redis, default_configs=RATE_LIMIT_CONFIGS)

            # Sources
            sources: list[NewsSourcePort] = []

            if settings.naver_client_id and settings.naver_client_secret:
                sources.append(
                    NaverNewsClient(
                        client_id=settings.naver_client_id,
                        client_secret=settings.naver_client_secret,
                        http_client=http_client,
                    )
                )

            if settings.newsdata_api_key:
                sources.append(
                    NewsDataClient(
                        api_key=settings.newsdata_api_key,
                        http_client=http_client,
                    )
                )

            # Aggregator
            aggregator = NewsAggregatorService()

            # OG Image Extractor (이미지 없는 기사 보강)
            og_extractor = OGImageExtractor(
                http_client=http_client,
                timeout=5.0,
                max_concurrent=10,
            )

            # Command (UseCase)
            yield FetchNewsCommand(
                news_sources=sources,
                news_cache=cache,
                aggregator=aggregator,
                cache_ttl=settings.news_cache_ttl,
                og_extractor=og_extractor,
                rate_limiter=rate_limiter,
            )
        finally:
            await redis.aclose()
