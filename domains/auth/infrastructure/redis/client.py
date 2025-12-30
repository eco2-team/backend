from functools import lru_cache

from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError, TimeoutError

from domains.auth.setup.config import get_settings

# Redis connection pool health check interval (seconds)
# Prevents "Connection closed by server" errors from idle connections
HEALTH_CHECK_INTERVAL = 30

# Connection pool settings
MAX_CONNECTIONS = 50
SOCKET_CONNECT_TIMEOUT = 5.0  # seconds
SOCKET_TIMEOUT = 5.0  # seconds

# Retry settings
RETRY_ON_ERROR = [ConnectionError, TimeoutError]
MAX_RETRIES = 3


def _build_client(url: str) -> Redis:
    """Build Redis client with robust connection settings.

    Key configurations:
    - socket_keepalive: Prevents connection drops from network inactivity
    - retry: Auto-reconnect on transient failures (ConnectionError, TimeoutError)
    - health_check_interval: Periodic connection validation
    - max_connections: Connection pool size limit
    """
    retry = Retry(ExponentialBackoff(), retries=MAX_RETRIES)

    return Redis.from_url(
        url,
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
def get_blacklist_redis() -> Redis:
    settings = get_settings()
    return _build_client(settings.redis_blacklist_url)


@lru_cache
def get_oauth_state_redis() -> Redis:
    settings = get_settings()
    return _build_client(settings.redis_oauth_state_url)
