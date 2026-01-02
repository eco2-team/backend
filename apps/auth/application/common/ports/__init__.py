"""Application Ports (Gateway Interfaces).

공용 포트만 정의합니다. 도메인별 포트는 해당 도메인에서 직접 import하세요:
  - apps.auth.application.oauth.ports.*
  - apps.auth.application.token.ports.*
  - apps.auth.application.users.ports.*
  - apps.auth.application.audit.ports.*
"""

from apps.auth.application.common.ports.flusher import Flusher
from apps.auth.application.common.ports.transaction_manager import TransactionManager

__all__ = [
    "Flusher",
    "TransactionManager",
]
