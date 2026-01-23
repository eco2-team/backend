"""Location 도메인 예외."""

from location.domain.exceptions.base import DomainError


class LocationNotFoundError(DomainError):
    """장소를 찾을 수 없음."""

    def __init__(self) -> None:
        super().__init__("Location not found")
