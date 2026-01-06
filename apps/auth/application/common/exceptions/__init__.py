"""Application Exceptions.

공통 예외만 포함합니다. 도메인별 예외는 각 도메인에서 직접 import하세요:
  - apps.auth.application.oauth.exceptions.*
  - apps.auth.application.token.exceptions.*
  - apps.auth.application.users.exceptions.*
"""

from apps.auth.application.common.exceptions.base import ApplicationError
from apps.auth.application.common.exceptions.gateway import (
    DataMapperError,
    GatewayError,
)

__all__ = [
    "ApplicationError",
    "GatewayError",
    "DataMapperError",
]
