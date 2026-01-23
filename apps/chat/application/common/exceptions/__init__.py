"""Chat 애플리케이션 예외."""

from chat.application.common.exceptions.auth import UnauthorizedError
from chat.application.common.exceptions.base import ApplicationError
from chat.application.common.exceptions.validation import MessageRequiredError

__all__ = [
    "ApplicationError",
    "UnauthorizedError",
    "MessageRequiredError",
]
