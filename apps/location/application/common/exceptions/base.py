"""애플리케이션 예외 베이스 클래스."""


class ApplicationError(Exception):
    """모든 애플리케이션 예외의 베이스 클래스."""

    def __init__(self, message: str = "Application error occurred") -> None:
        self.message = message
        super().__init__(message)
