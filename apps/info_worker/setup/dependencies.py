"""Dependency Injection for Info Worker.

Celery Task에서 사용할 의존성 팩토리.
리소스 풀링으로 메모리 누수 방지.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import asyncpg
import httpx
from redis.asyncio import Redis

from info.application.services.news_aggregator import NewsAggregatorService
from info.infrastructure.cache.redis_news_cache import RedisNewsCache
from info.infrastructure.integrations.naver.naver_news_client import NaverNewsClient
from info.infrastructure.integrations.newsdata.newsdata_client import NewsDataClient
from info.infrastructure.integrations.og.og_image_extractor import OGImageExtractor
from info_worker.application.commands.collect_news_command import CollectNewsCommand
from info_worker.infrastructure.persistence.postgres_news_repository import (
    PostgresNewsRepository,
)
from info_worker.setup.config import get_settings

if TYPE_CHECKING:
    from info_worker.application.ports.news_source import NewsSourcePort

logger = logging.getLogger(__name__)


# ============================================================
# Singleton Resources (Worker Lifecycle)
# ============================================================
_pg_pool: asyncpg.Pool | None = None
_redis: Redis | None = None
_http_client: httpx.AsyncClient | None = None


async def get_pg_pool() -> asyncpg.Pool:
    """PostgreSQL connection pool (싱글톤).

    Worker lifecycle 동안 유지.
    """
    global _pg_pool
    if _pg_pool is None:
        settings = get_settings()
        # asyncpg는 순수 postgresql:// 스킴만 지원
        # SQLAlchemy 스타일(postgresql+asyncpg://) → postgresql://로 변환
        dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        _pg_pool = await asyncpg.create_pool(
            dsn,
            min_size=2,
            max_size=10,
            command_timeout=30,
            max_inactive_connection_lifetime=300,
        )
        logger.info("PostgreSQL pool created")
    return _pg_pool


async def get_redis() -> Redis:
    """Redis client (싱글톤).

    Worker lifecycle 동안 유지.
    """
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=10,
        )
        logger.info("Redis client created")
    return _redis


async def get_http_client() -> httpx.AsyncClient:
    """HTTP client (싱글톤).

    Worker lifecycle 동안 유지. 리소스 누수 방지.
    """
    global _http_client
    if _http_client is None:
        settings = get_settings()
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=5.0,
                read=settings.naver_api_timeout,
                write=5.0,
                pool=10.0,
            ),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
            ),
        )
        logger.info("HTTP client created")
    return _http_client


# ============================================================
# Factory Functions
# ============================================================
def get_news_aggregator() -> NewsAggregatorService:
    """NewsAggregatorService 팩토리."""
    return NewsAggregatorService()


async def get_naver_client() -> NaverNewsClient | None:
    """NaverNewsClient 팩토리.

    싱글톤 HTTP 클라이언트 사용.
    """
    settings = get_settings()
    if not settings.naver_client_id or not settings.naver_client_secret:
        return None

    http_client = await get_http_client()
    return NaverNewsClient(
        client_id=settings.naver_client_id,
        client_secret=settings.naver_client_secret,
        http_client=http_client,
    )


async def get_newsdata_client() -> NewsDataClient | None:
    """NewsDataClient 팩토리.

    싱글톤 HTTP 클라이언트 사용.
    """
    settings = get_settings()
    if not settings.newsdata_api_key:
        return None

    http_client = await get_http_client()
    return NewsDataClient(
        api_key=settings.newsdata_api_key,
        http_client=http_client,
    )


async def get_og_extractor() -> OGImageExtractor:
    """OGImageExtractor 팩토리.

    싱글톤 HTTP 클라이언트 사용.
    """
    http_client = await get_http_client()
    return OGImageExtractor(
        http_client=http_client,
        timeout=5.0,
        max_concurrent=10,
    )


# ============================================================
# Command Factory
# ============================================================
async def create_collect_news_command(
    sources: list[NewsSourcePort] | None = None,
) -> CollectNewsCommand:
    """CollectNewsCommand 팩토리.

    Args:
        sources: 사용할 뉴스 소스 (None이면 모든 소스 사용)

    Returns:
        CollectNewsCommand 인스턴스
    """
    settings = get_settings()

    # DB & Cache (싱글톤)
    pg_pool = await get_pg_pool()
    redis = await get_redis()

    # Repository & Cache
    news_repository = PostgresNewsRepository(pool=pg_pool)
    news_cache = RedisNewsCache(redis=redis, ttl=settings.news_cache_ttl)

    # Sources
    if sources is None:
        sources = []
        naver = await get_naver_client()
        if naver:
            sources.append(naver)
        newsdata = await get_newsdata_client()
        if newsdata:
            sources.append(newsdata)

    # Aggregator & OG Extractor
    aggregator = get_news_aggregator()
    og_extractor = await get_og_extractor()

    return CollectNewsCommand(
        news_sources=sources,
        news_repository=news_repository,
        news_cache=news_cache,
        aggregator=aggregator,
        og_extractor=og_extractor,
        cache_ttl=settings.news_cache_ttl,
        cache_warm_limit=settings.cache_warm_limit,
    )


async def create_collect_news_command_newsdata_only() -> CollectNewsCommand:
    """NewsData 전용 CollectNewsCommand 팩토리.

    NewsData.io는 30분 주기로 별도 스케줄링 (Rate Limit 대응).
    """
    newsdata = await get_newsdata_client()
    sources = [newsdata] if newsdata else []

    return await create_collect_news_command(sources=sources)


# ============================================================
# Lifecycle Management
# ============================================================
async def cleanup() -> None:
    """리소스 정리.

    Worker 종료 시 호출.
    """
    global _pg_pool, _redis, _http_client

    if _http_client:
        await _http_client.aclose()
        _http_client = None
        logger.info("HTTP client closed")

    if _pg_pool:
        await _pg_pool.close()
        _pg_pool = None
        logger.info("PostgreSQL pool closed")

    if _redis:
        await _redis.aclose()
        _redis = None
        logger.info("Redis client closed")
