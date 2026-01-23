"""검증 관련 예외."""


class ApplicationError(Exception):
    """모든 애플리케이션 예외의 베이스 클래스."""

    def __init__(self, message: str = "Application error occurred") -> None:
        self.message = message
        super().__init__(message)


class InvalidCategoryError(ApplicationError):
    """유효하지 않은 카테고리."""

    def __init__(self, valid_categories: list[str]) -> None:
        super().__init__(f"Invalid category. Must be one of: {valid_categories}")


class InvalidSourceError(ApplicationError):
    """유효하지 않은 뉴스 소스."""

    def __init__(self, valid_sources: list[str]) -> None:
        super().__init__(f"Invalid source. Must be one of: {valid_sources}")


class InvalidCursorFormatError(ApplicationError):
    """유효하지 않은 커서 형식."""

    def __init__(self) -> None:
        super().__init__("Invalid cursor format. Must be a numeric timestamp or timestamp_id.")
