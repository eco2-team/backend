"""Blacklist Event Publisher for ext-authz Local Cache Sync.

When a token is blacklisted (logout), this publisher sends an event to RabbitMQ.
ext-authz pods consume these events and update their local cache.

Architecture:
    auth-api (logout)
        │
        └─→ RabbitMQ (blacklist.events fanout)
                │
                ├─→ ext-authz Pod 1: cache.Add(jti, exp)
                ├─→ ext-authz Pod 2: cache.Add(jti, exp)
                └─→ ext-authz Pod N: cache.Add(jti, exp)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from domains.auth.core.config import get_settings

logger = logging.getLogger(__name__)

# Lazy import to avoid dependency issues when RabbitMQ is not configured
_publisher: Optional["BlacklistEventPublisher"] = None


def get_blacklist_publisher() -> Optional["BlacklistEventPublisher"]:
    """Get singleton publisher instance. Returns None if AMQP is not configured."""
    global _publisher
    if _publisher is None:
        settings = get_settings()
        if settings.amqp_url:
            try:
                _publisher = BlacklistEventPublisher(settings.amqp_url)
                logger.info("Blacklist event publisher initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize blacklist publisher: {e}")
                return None
        else:
            logger.debug("AMQP_URL not configured, blacklist events disabled")
            return None
    return _publisher


class BlacklistEventPublisher:
    """Publishes blacklist events to RabbitMQ fanout exchange."""

    EXCHANGE_NAME = "blacklist.events"
    EXCHANGE_TYPE = "fanout"

    def __init__(self, amqp_url: str):
        self.amqp_url = amqp_url
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
        """Publish blacklist add event.

        Args:
            jti: JWT token identifier
            expires_at: When the token expires

        Returns:
            True if published successfully, False otherwise
        """
        try:
            self._ensure_connection()

            event = {
                "type": "add",
                "jti": jti,
                "expires_at": expires_at.isoformat(),
            }

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
            logger.error(f"Failed to publish blacklist event: {e}")
            # Reset connection for next attempt
            self._connection = None
            self._channel = None
            return False

    def close(self):
        """Close connection to RabbitMQ."""
        if self._connection and not self._connection.is_closed:
            self._connection.close()
            logger.debug("Closed RabbitMQ connection")
