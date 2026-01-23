"""Scan 도메인 예외."""

from scan.domain.exceptions.base import DomainError
from scan.domain.exceptions.scan import ResultNotFoundError, UnsupportedModelError

__all__ = [
    "DomainError",
    "ResultNotFoundError",
    "UnsupportedModelError",
]
