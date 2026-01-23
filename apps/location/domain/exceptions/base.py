"""도메인 예외 베이스 클래스."""


class DomainError(Exception):
    """모든 도메인 예외의 베이스 클래스."""

    def __init__(self, message: str = "Domain error occurred") -> None:
        self.message = message
        super().__init__(message)
