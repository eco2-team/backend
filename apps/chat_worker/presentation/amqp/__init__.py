"""AMQP/Taskiq Presentation Layer.

Chat Worker의 외부 진입점.
RabbitMQ AMQP 프로토콜을 통해 메시지를 수신합니다.

프로토콜: AMQP 0-9-1 (RabbitMQ)
라이브러리: Taskiq + aio-pika
Exchange: chat_tasks (direct)
Queue: chat.process

Tasks:
- process_chat: Chat 파이프라인 실행
- health_check: Worker 헬스체크
"""

from .process_task import health_check, process_chat

__all__ = ["health_check", "process_chat"]
