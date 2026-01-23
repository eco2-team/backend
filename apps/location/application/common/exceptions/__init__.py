"""Application Exceptions."""

from location.application.common.exceptions.base import ApplicationError
from location.application.common.exceptions.validation import (
    InvalidPickupCategoryError,
    InvalidStoreCategoryError,
    KakaoApiUnavailableError,
    ServiceUnavailableError,
)

__all__ = [
    "ApplicationError",
    "InvalidPickupCategoryError",
    "InvalidStoreCategoryError",
    "KakaoApiUnavailableError",
    "ServiceUnavailableError",
]
