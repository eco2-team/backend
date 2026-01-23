"""Scan 애플리케이션 예외."""

from scan.application.common.exceptions.auth import UnauthorizedError
from scan.application.common.exceptions.base import ApplicationError
from scan.application.common.exceptions.validation import ImageUrlRequiredError

__all__ = [
    "ApplicationError",
    "UnauthorizedError",
    "ImageUrlRequiredError",
]
