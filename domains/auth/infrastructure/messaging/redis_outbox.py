"""Redis Outbox Repository Adapter.

This module implements the OutboxRepository port using Redis.
It handles the actual Redis operations for the Outbox pattern.

Architecture (Hexagonal / Ports & Adapters):
    Application Layer:
        ├── Services (BlacklistEventPublisher)
        │       │
        │       └── uses ─► OutboxRepository (Port)
        │                   [application/ports/outbox.py]
        │
    Infrastructure Layer:
        └── Adapters
                └── RedisOutboxRepository (THIS FILE)
                        │
                        └── redis-py (External Library)

Reference: https://github.com/ivan-borovets/fastapi-clean-example
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis import Redis

logger = logging.getLogger(__name__)


class RedisOutboxRepository:
    """Redis-based implementation of OutboxRepository.

    Uses Redis List for FIFO queue:
        - push(): LPUSH (add to head)
        - pop(): RPOP (remove from tail)
    """

    def __init__(self, redis_url: str):
        """Initialize Redis connection.

        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379/0)
        """
        import redis

        self._redis: Redis = redis.from_url(redis_url)
        self._redis_url = redis_url
        logger.debug(f"RedisOutboxRepository initialized: {redis_url[:20]}...")

    def push(self, key: str, data: str) -> bool:
        """Push data to the outbox queue (LPUSH for FIFO).

        Args:
            key: The outbox queue key
            data: JSON-serialized event data

        Returns:
            True if successful, False otherwise
        """
        try:
            self._redis.lpush(key, data)
            logger.debug(f"Pushed to outbox: key={key}")
            return True
        except Exception as e:
            logger.exception(f"Failed to push to outbox: {e}")
            return False

    def pop(self, key: str) -> str | None:
        """Pop data from the outbox queue (RPOP for FIFO).

        Args:
            key: The outbox queue key

        Returns:
            JSON-serialized event data, or None if empty
        """
        try:
            result = self._redis.rpop(key)
            if result is None:
                return None
            # Redis returns bytes, decode to string
            return result.decode("utf-8") if isinstance(result, bytes) else result
        except Exception as e:
            logger.exception(f"Failed to pop from outbox: {e}")
            return None

    def length(self, key: str) -> int:
        """Get the length of the outbox queue.

        Args:
            key: The outbox queue key

        Returns:
            Number of items in the queue
        """
        try:
            return self._redis.llen(key)
        except Exception as e:
            logger.exception(f"Failed to get outbox length: {e}")
            return 0
