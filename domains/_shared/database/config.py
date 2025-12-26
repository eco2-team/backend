"""
Database Pool Configuration Module

환경변수 기반 DB 커넥션 풀 설정.
Worker(Integration Layer)에서 주로 사용되며, API는 점진적으로 DB 직접 접근을 줄여감.

Pool 크기 가이드라인:
- API 서비스: pool_size=5, max_overflow=10 (기본값, 읽기 위주)
- Worker 서비스: pool_size=10~20, max_overflow=15~30 (쓰기 집중)
"""

from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabasePoolSettings(BaseSettings):
    """Database connection pool settings.

    환경변수로 오버라이드 가능:
    - DB_POOL_SIZE: 상시 유지 커넥션 수
    - DB_MAX_OVERFLOW: 초과 허용 커넥션 수
    - DB_POOL_TIMEOUT: 커넥션 획득 대기 시간 (초)
    - DB_POOL_RECYCLE: 커넥션 재생성 주기 (초)
    - DB_POOL_PRE_PING: 커넥션 유효성 사전 검사
    """

    pool_size: int = Field(
        default=5,
        description="Number of connections to keep open (pool_size)",
        ge=1,
        le=100,
    )

    max_overflow: int = Field(
        default=10,
        description="Number of connections to allow beyond pool_size",
        ge=0,
        le=100,
    )

    pool_timeout: int = Field(
        default=30,
        description="Seconds to wait for a connection from pool",
        ge=1,
        le=300,
    )

    pool_recycle: int = Field(
        default=1800,  # 30분
        description="Seconds after which to recycle connections",
        ge=60,
        le=7200,
    )

    pool_pre_ping: bool = Field(
        default=True,
        description="Test connections before use",
    )

    echo: bool = Field(
        default=False,
        description="Log all SQL statements",
    )

    model_config = SettingsConfigDict(
        env_prefix="DB_",
        case_sensitive=False,
        extra="ignore",
    )

    def get_engine_kwargs(self) -> dict[str, Any]:
        """Return kwargs for create_async_engine().

        Usage:
            from domains._shared.database.config import get_db_pool_settings

            settings = get_db_pool_settings()
            engine = create_async_engine(
                database_url,
                **settings.get_engine_kwargs(),
            )
        """
        return {
            "pool_size": self.pool_size,
            "max_overflow": self.max_overflow,
            "pool_timeout": self.pool_timeout,
            "pool_recycle": self.pool_recycle,
            "pool_pre_ping": self.pool_pre_ping,
            "echo": self.echo,
        }


# Worker 전용 프리셋 (높은 동시성)
class WorkerDatabasePoolSettings(DatabasePoolSettings):
    """Worker 전용 DB 풀 설정.

    gevent/threads pool에서 높은 concurrency를 지원하기 위해
    기본값이 더 높게 설정됨.
    """

    pool_size: int = Field(
        default=15,
        description="Worker pool size (higher for batch operations)",
        ge=1,
        le=100,
    )

    max_overflow: int = Field(
        default=20,
        description="Worker max overflow (higher for burst traffic)",
        ge=0,
        le=100,
    )


@lru_cache
def get_db_pool_settings() -> DatabasePoolSettings:
    """Get cached database pool settings (API용)."""
    return DatabasePoolSettings()


@lru_cache
def get_worker_db_pool_settings() -> WorkerDatabasePoolSettings:
    """Get cached worker database pool settings."""
    return WorkerDatabasePoolSettings()
