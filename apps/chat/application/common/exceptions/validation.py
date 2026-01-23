"""검증 관련 애플리케이션 예외."""

from chat.application.common.exceptions.base import ApplicationError


class MessageRequiredError(ApplicationError):
    """메시지 필수 입력 누락."""

    def __init__(self) -> None:
        super().__init__("message is required")
