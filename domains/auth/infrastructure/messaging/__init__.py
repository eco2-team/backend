"""Messaging infrastructure - RabbitMQ, Outbox."""

from domains.auth.infrastructure.messaging.redis_outbox import RedisOutboxRepository

__all__ = ["RedisOutboxRepository"]
