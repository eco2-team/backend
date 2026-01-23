"""인증 관련 애플리케이션 예외."""

from scan.application.common.exceptions.base import ApplicationError


class UnauthorizedError(ApplicationError):
    """인증 실패."""

    def __init__(self, reason: str = "Unauthorized: X-User-ID header is required") -> None:
        super().__init__(reason)
