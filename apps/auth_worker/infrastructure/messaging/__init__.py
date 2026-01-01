"""Messaging Infrastructure.

메시지 브로커 연결을 담당합니다.

블로그 참고: https://rooftopsnow.tistory.com/126
- RabbitMQClient: MQ 연결/채널/메시지 스트림 (Infrastructure)
- ConsumerAdapter: decode/dispatch/ack-nack (Presentation)
"""

from apps.auth_worker.infrastructure.messaging.rabbitmq_client import RabbitMQClient

__all__ = ["RabbitMQClient"]
