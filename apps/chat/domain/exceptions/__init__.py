"""Chat 도메인 예외."""

from chat.domain.exceptions.base import DomainError
from chat.domain.exceptions.chat import ChatAccessDeniedError, ChatNotFoundError

__all__ = [
    "DomainError",
    "ChatNotFoundError",
    "ChatAccessDeniedError",
]
