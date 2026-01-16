"""Info Worker Configuration."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Info Worker 설정."""

    # Environment
    environment: str = "local"
    debug: bool = False

    # Celery
    celery_broker_url: str = "amqp://guest:guest@localhost:5672/"
    celery_result_backend: str | None = None

    # PostgreSQL
    database_url: str = "postgresql://postgres:postgres@localhost:5432/eco2"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # 네이버 검색 API
    naver_client_id: str | None = None
    naver_client_secret: str | None = None
    naver_api_timeout: float = 10.0

    # NewsData.io API
    newsdata_api_key: str | None = None
    newsdata_api_timeout: float = 10.0

    # 캐시 설정
    news_cache_ttl: int = 3600  # 1시간
    news_article_ttl: int = 86400  # 24시간
    cache_warm_limit: int = 200  # 캐시 워밍 시 최대 기사 수

    # 수집 스케줄 (초)
    collect_interval_naver: int = 300  # 5분
    collect_interval_newsdata: int = 1800  # 30분

    # Logging
    log_level: str = "INFO"

    class Config:
        env_prefix = "INFO_WORKER_"
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤."""
    return Settings()
