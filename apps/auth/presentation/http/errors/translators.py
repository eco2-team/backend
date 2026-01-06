"""Error Translators.

도메인 예외를 HTTP 상태 코드로 변환합니다.
"""

from apps.auth.domain.exceptions.auth import (
    InvalidTokenError,
    TokenExpiredError,
    TokenRevokedError,
)
from apps.auth.domain.exceptions.base import DomainError
from apps.auth.domain.exceptions.user import UserNotFoundError


def translate_domain_error(exc: DomainError) -> tuple[int, str]:
    """도메인 예외를 (status_code, code) 튜플로 변환.

    Returns:
        (HTTP 상태 코드, 에러 코드)
    """
    if isinstance(exc, UserNotFoundError):
        return 404, "USER_NOT_FOUND"
    if isinstance(exc, (InvalidTokenError, TokenExpiredError, TokenRevokedError)):
        return 401, "UNAUTHORIZED"
    return 400, "DOMAIN_ERROR"
