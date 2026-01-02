"""Users Gateway Exceptions."""

from apps.auth.application.common.exceptions.base import ApplicationError


class UserServiceUnavailableError(ApplicationError):
    """Users 서비스 통신 실패.

    gRPC 통신 오류, Circuit Breaker 열림 등으로 인해
    users 도메인과 통신할 수 없는 경우 발생합니다.
    """

    def __init__(self, reason: str = "Users service unavailable") -> None:
        super().__init__(reason)
