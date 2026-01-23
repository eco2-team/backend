"""도메인 예외 베이스 클래스."""


class DomainError(Exception):
    """모든 도메인 예외의 베이스 클래스.

    도메인 레이어에서 발생하는 비즈니스 규칙 위반을 나타냅니다.
    Presentation 레이어에서 HTTP 응답으로 변환됩니다.
    """

    def __init__(self, message: str = "Domain error occurred") -> None:
        self.message = message
        super().__init__(message)
