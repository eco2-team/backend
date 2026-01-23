"""인증 관련 예외."""


class MissingUserIdError(Exception):
    """사용자 ID 헤더가 누락됨."""

    def __init__(self) -> None:
        self.message = "Missing x-user-id header"
        super().__init__(self.message)


class InvalidUserIdFormatError(Exception):
    """유효하지 않은 사용자 ID 형식."""

    def __init__(self) -> None:
        self.message = "Invalid x-user-id format"
        super().__init__(self.message)
