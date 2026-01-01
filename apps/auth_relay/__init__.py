"""Auth Relay Worker.

Redis Outbox에서 실패한 블랙리스트 이벤트를 RabbitMQ로 재발행하는 워커입니다.
"""
