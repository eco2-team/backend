"""애플리케이션 예외 베이스 클래스."""


class ApplicationError(Exception):
    """모든 애플리케이션 예외의 베이스 클래스.

    Use Case 실행 중 발생하는 예외를 나타냅니다.
    """

    def __init__(self, message: str = "Application error occurred") -> None:
        self.message = message
        super().__init__(message)
