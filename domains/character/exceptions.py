"""Custom exceptions for Character service."""


class CharacterServiceError(Exception):
    """Base exception for Character service."""

    pass


class CatalogEmptyError(CharacterServiceError):
    """Raised when the character catalog is empty."""

    def __init__(self) -> None:
        super().__init__("등록된 캐릭터가 없습니다.")
