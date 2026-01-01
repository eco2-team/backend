"""Messaging Infrastructure.

RabbitMQ 발행 구현체입니다.
"""

from apps.auth_relay.infrastructure.messaging.rabbitmq_publisher import (
    RabbitMQEventPublisher,
)

__all__ = ["RabbitMQEventPublisher"]
