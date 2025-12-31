"""Application Exceptions."""

from apps.users.application.common.exceptions.base import ApplicationError
from apps.users.application.common.exceptions.user import (
    UserNotFoundError,
    InvalidPhoneNumberError,
    NoChangesProvidedError,
)

__all__ = [
    "ApplicationError",
    "UserNotFoundError",
    "InvalidPhoneNumberError",
    "NoChangesProvidedError",
]
