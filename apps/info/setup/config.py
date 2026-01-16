"""Info Service Configuration."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Info Service 설정."""

    # Environment
    environment: str = "local"
    debug: bool = False

    # CORS (production: 명시적 origins 필수)
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # PostgreSQL (Fallback용)
    database_url: str | None = None

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

    # 페이지네이션
    news_default_limit: int = 10
    news_max_limit: int = 50

    # Logging
    log_level: str = "INFO"

    class Config:
        env_prefix = "INFO_"
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤."""
    return Settings()
