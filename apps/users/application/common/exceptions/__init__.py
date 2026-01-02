"""Application Exceptions.

공통 예외만 포함합니다. 도메인별 예외는 각 도메인에서 직접 import하세요:
  - apps.users.application.profile.exceptions.*
"""

from apps.users.application.common.exceptions.base import ApplicationError

__all__ = [
    "ApplicationError",
]
