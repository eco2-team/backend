"""Consumer Presentation Layer.

RabbitMQ 메시지를 수신하여 배치 저장.
"""

from .adapter import MessageSaveConsumerAdapter
from .handler import MessageSaveHandler

__all__ = [
    "MessageSaveConsumerAdapter",
    "MessageSaveHandler",
]
