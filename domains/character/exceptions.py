"""Custom exceptions for Character service."""


class CharacterServiceError(Exception):
    """Base exception for Character service."""

    pass


class CharacterNotFoundError(CharacterServiceError):
    """Raised when a character definition cannot be found."""

    def __init__(self, name: str | None = None, character_id: str | None = None) -> None:
        self.name = name
        self.character_id = character_id
        if name:
            message = f"Character not found: {name}"
        elif character_id:
            message = f"Character not found: {character_id}"
        else:
            message = "Character not found"
        super().__init__(message)


class CatalogEmptyError(CharacterServiceError):
    """Raised when the character catalog is empty."""

    def __init__(self) -> None:
        super().__init__("등록된 캐릭터가 없습니다.")


class CharacterNameRequiredError(CharacterServiceError):
    """Raised when character name is required but not provided."""

    def __init__(self) -> None:
        super().__init__("Character name required")


class DefaultCharacterNotConfiguredError(CharacterServiceError):
    """Raised when default character name is not configured."""

    def __init__(self) -> None:
        super().__init__("Default character name is not configured")
