"""인증 관련 예외."""

from __future__ import annotations

from users.application.common.exceptions.base import ApplicationError


class MissingUserIdError(ApplicationError):
    """사용자 ID가 누락됨."""

    def __init__(self) -> None:
        super().__init__("Missing user ID")


class InvalidUserIdFormatError(ApplicationError):
    """유효하지 않은 사용자 ID 형식."""

    def __init__(self) -> None:
        super().__init__("Invalid user ID format")
