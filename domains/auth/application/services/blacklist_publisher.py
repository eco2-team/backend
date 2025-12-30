"""Blacklist Event Publisher for ext-authz Local Cache Sync.

When a token is blacklisted (logout), this publisher sends an event to RabbitMQ.
ext-authz pods consume these events and update their local cache.

Architecture (Outbox Pattern with Clean Architecture):

    Business Layer:
        BlacklistEventPublisher
            │
            ├── RabbitMQ (direct publish, ~99% success)
            │
            └── OutboxRepository (Interface) ◄── Dependency Inversion
                    │
    Integration Layer:
                    └── RedisOutboxRepository (Adapter)
                            │
                            └── Relay Worker: RPOP → RabbitMQ 재발행

Redis Keys:
    - outbox:blacklist        # List: 실패한 이벤트 (FIFO)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from domains.auth.setup.config import get_settings

if TYPE_CHECKING:
    from domains.auth.application.ports.outbox import OutboxRepository

logger = logging.getLogger(__name__)

# Redis Outbox key for failed MQ publishes
OUTBOX_KEY = "outbox:blacklist"

# Lazy import to avoid dependency issues when RabbitMQ is not configured
_publisher: Optional["BlacklistEventPublisher"] = None


def get_blacklist_publisher() -> Optional["BlacklistEventPublisher"]:
    """Get singleton publisher instance. Returns None if AMQP is not configured."""
    global _publisher
    if _publisher is None:
        settings = get_settings()
        if settings.amqp_url:
            try:
                # Create outbox repository if Redis is configured
                outbox = _create_outbox_repository()
                _publisher = BlacklistEventPublisher(settings.amqp_url, outbox=outbox)
                logger.info("Blacklist event publisher initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize blacklist publisher: {e}")
                return None
        else:
            logger.debug("AMQP_URL not configured, blacklist events disabled")
            return None
    return _publisher


def _create_outbox_repository() -> Optional["OutboxRepository"]:
    """Create outbox repository from environment configuration.

    Returns:
        RedisOutboxRepository if AUTH_REDIS_URL is set, None otherwise
    """
    redis_url = os.getenv("AUTH_REDIS_URL")
    if not redis_url:
        logger.warning("AUTH_REDIS_URL not set, outbox fallback disabled")
        return None

    try:
        from domains.auth.infrastructure.messaging.redis_outbox import RedisOutboxRepository

        return RedisOutboxRepository(redis_url)
    except Exception as e:
        logger.warning(f"Failed to create outbox repository: {e}")
        return None


class BlacklistEventPublisher:
    """Publishes blacklist events to RabbitMQ fanout exchange.

    Uses Dependency Injection for the outbox repository,
    following Clean Architecture principles.
    """

    EXCHANGE_NAME = "blacklist.events"
    EXCHANGE_TYPE = "fanout"

    def __init__(
        self,
        amqp_url: str,
        outbox: Optional["OutboxRepository"] = None,
    ):
        """Initialize publisher with optional outbox repository.

        Args:
            amqp_url: RabbitMQ connection URL
            outbox: Optional outbox repository for fallback (DI)
        """
        self.amqp_url = amqp_url
        self._outbox = outbox
        self._connection = None
        self._channel = None

    def _ensure_connection(self):
        """Lazily establish connection to RabbitMQ."""
        if self._connection is None or self._connection.is_closed:
            import pika

            params = pika.URLParameters(self.amqp_url)
            self._connection = pika.BlockingConnection(params)
            self._channel = self._connection.channel()

            # Declare fanout exchange
            self._channel.exchange_declare(
                exchange=self.EXCHANGE_NAME,
                exchange_type=self.EXCHANGE_TYPE,
                durable=True,
            )
            logger.debug(f"Connected to RabbitMQ, exchange={self.EXCHANGE_NAME}")

    def publish_add(self, jti: str, expires_at: datetime) -> bool:
        """Publish blacklist add event with Outbox fallback.

        1차 시도: RabbitMQ 직접 발행
        실패 시: Outbox Repository에 적재 (Relay Worker가 재처리)

        Args:
            jti: JWT token identifier
            expires_at: When the token expires

        Returns:
            True if published directly, False if queued to outbox
        """
        event = {
            "type": "add",
            "jti": jti,
            "expires_at": expires_at.isoformat(),
            "timestamp": datetime.utcnow().isoformat(),
        }

        try:
            self._ensure_connection()

            import pika

            self._channel.basic_publish(
                exchange=self.EXCHANGE_NAME,
                routing_key="",  # Ignored for fanout
                body=json.dumps(event),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,  # Persistent
                ),
            )

            logger.debug(f"Published blacklist event: jti={jti[:8]}...")
            return True

        except Exception as e:
            logger.warning(
                f"MQ publish failed, queueing to outbox: {e}",
                extra={"jti": jti[:8]},
            )
            # Reset connection for next attempt
            self._connection = None
            self._channel = None
            # Queue to Outbox Repository for Relay Worker
            self._queue_to_outbox(event)
            return False

    def _queue_to_outbox(self, event: dict) -> bool:
        """Queue event to Outbox Repository for later processing by Relay Worker.

        Args:
            event: Event dict to queue

        Returns:
            True if queued successfully, False otherwise
        """
        if self._outbox is None:
            logger.error(
                "Outbox repository not configured, event lost",
                extra={"jti": event.get("jti", "")[:8]},
            )
            return False

        try:
            success = self._outbox.push(OUTBOX_KEY, json.dumps(event))
            if success:
                logger.info(
                    "Event queued to outbox",
                    extra={"jti": event.get("jti", "")[:8]},
                )
            return success
        except Exception as e:
            logger.exception(
                f"Failed to queue to outbox, event lost: {e}",
                extra={"jti": event.get("jti", "")[:8]},
            )
            return False

    def close(self):
        """Close connection to RabbitMQ."""
        if self._connection and not self._connection.is_closed:
            self._connection.close()
            logger.debug("Closed RabbitMQ connection")
