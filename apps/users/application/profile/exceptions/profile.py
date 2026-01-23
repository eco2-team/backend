"""Profile domain exceptions."""

from __future__ import annotations

from users.application.common.exceptions.base import ApplicationError


class UserNotFoundError(ApplicationError):
    """사용자를 찾을 수 없을 때 발생하는 예외."""

    def __init__(self) -> None:
        super().__init__("User not found")


class InvalidPhoneNumberError(ApplicationError):
    """유효하지 않은 전화번호 형식."""

    def __init__(self, message: str = "Invalid phone number format") -> None:
        super().__init__(message)


class NoChangesProvidedError(ApplicationError):
    """변경사항이 없을 때 발생하는 예외."""

    def __init__(self) -> None:
        super().__init__("No changes provided")
