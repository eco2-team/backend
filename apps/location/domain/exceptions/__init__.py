"""도메인 예외."""

from location.domain.exceptions.base import DomainError
from location.domain.exceptions.location import LocationNotFoundError

__all__ = [
    "DomainError",
    "LocationNotFoundError",
]
