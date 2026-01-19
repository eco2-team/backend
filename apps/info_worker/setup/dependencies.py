"""Dependency Injection for Info Worker.

Celery Task에서 사용할 의존성 팩토리.
gevent 호환을 위해 동기 드라이버 사용:
- psycopg2: PostgreSQL
- redis (sync): Cache
- httpx (sync): HTTP clients
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx
from psycopg2.pool import ThreadedConnectionPool
from redis import Redis

from info.application.services.news_aggregator import NewsAggregatorService
from info.infrastructure.cache.redis_news_cache import RedisNewsCacheSync
from info.infrastructure.integrations.naver.naver_news_client import NaverNewsClientSync
from info.infrastructure.integrations.newsdata.newsdata_client import NewsDataClientSync
from info.infrastructure.integrations.og.og_image_extractor import OGImageExtractorSync
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
_pg_pool: ThreadedConnectionPool | None = None
_redis: Redis | None = None
_http_client: httpx.Client | None = None


def get_pg_pool() -> ThreadedConnectionPool:
    """PostgreSQL connection pool (싱글톤).

    psycopg2 ThreadedConnectionPool - gevent 몽키패칭 호환.
    Worker lifecycle 동안 유지.
    """
    global _pg_pool
    if _pg_pool is None:
        settings = get_settings()
        # SQLAlchemy 스타일 DSN → psycopg2 스타일로 변환
        dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        _pg_pool = ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=dsn,
        )
        logger.info("PostgreSQL pool created (psycopg2)")
    return _pg_pool


def get_redis() -> Redis:
    """Redis client (싱글톤).

    동기 redis-py - gevent 몽키패칭 호환.
    Worker lifecycle 동안 유지.

    Resilience 설정:
    - health_check_interval: 30초마다 연결 상태 확인
    - socket_timeout: 10초 내 응답 없으면 타임아웃
    - socket_connect_timeout: 5초 내 연결 실패 시 타임아웃
    - retry_on_timeout: 타임아웃 시 자동 재시도
    """
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=10,
            # Resilience settings
            health_check_interval=30,
            retry_on_timeout=True,
        )
        logger.info("Redis client created (sync)")
    return _redis


def get_http_client() -> httpx.Client:
    """HTTP client (싱글톤).

    동기 httpx - gevent 몽키패칭 호환.
    Worker lifecycle 동안 유지. 리소스 누수 방지.
    """
    global _http_client
    if _http_client is None:
        settings = get_settings()
        _http_client = httpx.Client(
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
        logger.info("HTTP client created (sync)")
    return _http_client


# ============================================================
# Factory Functions
# ============================================================
def get_news_aggregator() -> NewsAggregatorService:
    """NewsAggregatorService 팩토리."""
    return NewsAggregatorService()


def get_naver_client() -> NaverNewsClientSync | None:
    """NaverNewsClient 팩토리 (동기).

    싱글톤 HTTP 클라이언트 사용.
    """
    settings = get_settings()
    if not settings.naver_client_id or not settings.naver_client_secret:
        return None

    http_client = get_http_client()
    return NaverNewsClientSync(
        client_id=settings.naver_client_id,
        client_secret=settings.naver_client_secret,
        http_client=http_client,
    )


def get_newsdata_client() -> NewsDataClientSync | None:
    """NewsDataClient 팩토리 (동기).

    싱글톤 HTTP 클라이언트 사용.
    """
    settings = get_settings()
    if not settings.newsdata_api_key:
        return None

    http_client = get_http_client()
    return NewsDataClientSync(
        api_key=settings.newsdata_api_key,
        http_client=http_client,
    )


def get_og_extractor() -> OGImageExtractorSync:
    """OGImageExtractor 팩토리 (동기).

    싱글톤 HTTP 클라이언트 사용.
    """
    http_client = get_http_client()
    return OGImageExtractorSync(
        http_client=http_client,
        timeout=5.0,
        max_concurrent=10,
    )


# ============================================================
# Command Factory
# ============================================================
def create_collect_news_command(
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
    pg_pool = get_pg_pool()
    redis = get_redis()

    # Repository & Cache
    news_repository = PostgresNewsRepository(pool=pg_pool)
    news_cache = RedisNewsCacheSync(redis=redis, ttl=settings.news_cache_ttl)

    # Sources
    if sources is None:
        sources = []
        naver = get_naver_client()
        if naver:
            sources.append(naver)
        newsdata = get_newsdata_client()
        if newsdata:
            sources.append(newsdata)

    # Aggregator & OG Extractor
    aggregator = get_news_aggregator()
    og_extractor = get_og_extractor()

    return CollectNewsCommand(
        news_sources=sources,
        news_repository=news_repository,
        news_cache=news_cache,
        aggregator=aggregator,
        og_extractor=og_extractor,
        cache_ttl=settings.news_cache_ttl,
        cache_warm_limit=settings.cache_warm_limit,
    )


def create_collect_news_command_newsdata_only() -> CollectNewsCommand:
    """NewsData 전용 CollectNewsCommand 팩토리.

    NewsData.io는 30분 주기로 별도 스케줄링 (Rate Limit 대응).
    """
    newsdata = get_newsdata_client()
    sources = [newsdata] if newsdata else []

    return create_collect_news_command(sources=sources)


# ============================================================
# Lifecycle Management
# ============================================================
def cleanup() -> None:
    """리소스 정리.

    Worker 종료 시 호출.
    """
    global _pg_pool, _redis, _http_client

    if _http_client:
        _http_client.close()
        _http_client = None
        logger.info("HTTP client closed")

    if _pg_pool:
        _pg_pool.closeall()
        _pg_pool = None
        logger.info("PostgreSQL pool closed")

    if _redis:
        _redis.close()
        _redis = None
        logger.info("Redis client closed")
