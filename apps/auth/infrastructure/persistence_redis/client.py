"""Redis Client Provider.

기존 domains/auth/infrastructure/redis/client.py와 호환.
블랙리스트용과 OAuth 상태용 클라이언트를 분리합니다.

Retry 설정 (domains 정합성):
    - ExponentialBackoff: 지수 백오프 재시도
    - MAX_RETRIES: 3회 재시도
    - ConnectionError, TimeoutError에서 자동 재시도
    - health_check_interval: 30초마다 연결 상태 확인
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError, TimeoutError

if TYPE_CHECKING:
    import redis.asyncio as aioredis

# Redis connection settings (domains 정합성)
HEALTH_CHECK_INTERVAL = 30  # seconds
MAX_CONNECTIONS = 50
SOCKET_CONNECT_TIMEOUT = 5.0  # seconds
SOCKET_TIMEOUT = 5.0  # seconds
RETRY_ON_ERROR = [ConnectionError, TimeoutError]
MAX_RETRIES = 3


def _build_async_client(redis_url: str) -> "aioredis.Redis":
    """비동기 Redis 클라이언트 생성.

    Key configurations:
    - socket_keepalive: 네트워크 비활성으로 인한 연결 끊김 방지
    - retry: 일시적 장애 시 자동 재연결 (ConnectionError, TimeoutError)
    - health_check_interval: 주기적 연결 검증
    - max_connections: 연결 풀 크기 제한
    """
    import redis.asyncio as aioredis

    retry = Retry(ExponentialBackoff(), retries=MAX_RETRIES)

    return aioredis.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=True,
        # Health & Keepalive
        health_check_interval=HEALTH_CHECK_INTERVAL,
        socket_keepalive=True,
        # Timeouts
        socket_connect_timeout=SOCKET_CONNECT_TIMEOUT,
        socket_timeout=SOCKET_TIMEOUT,
        # Connection Pool
        max_connections=MAX_CONNECTIONS,
        # Retry on transient errors
        retry=retry,
        retry_on_error=RETRY_ON_ERROR,
    )


@lru_cache
def get_blacklist_redis() -> "aioredis.Redis":
    """토큰 블랙리스트용 Redis 클라이언트.

    환경변수:
        - AUTH_REDIS_BLACKLIST_URL (default: redis://localhost:6379/0)
    """
    from apps.auth.setup.config import get_settings

    settings = get_settings()
    return _build_async_client(settings.redis_blacklist_url)


@lru_cache
def get_oauth_state_redis() -> "aioredis.Redis":
    """OAuth 상태 저장용 Redis 클라이언트.

    환경변수:
        - AUTH_REDIS_OAUTH_STATE_URL (default: redis://localhost:6379/3)
    """
    from apps.auth.setup.config import get_settings

    settings = get_settings()
    return _build_async_client(settings.redis_oauth_state_url)
