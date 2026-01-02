"""Authentication Exceptions."""

from apps.auth.application.common.exceptions.base import ApplicationError


class AuthenticationError(ApplicationError):
    """인증 실패."""

    def __init__(self, reason: str = "Authentication failed") -> None:
        super().__init__(reason)
