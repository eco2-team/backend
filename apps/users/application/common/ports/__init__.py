"""Application ports (gateway interfaces).

공용 포트만 정의합니다. 도메인별 포트는 해당 도메인에서 직접 import하세요:
  - apps.users.application.profile.ports.*
  - apps.users.application.identity.ports.*
  - apps.users.application.character.ports.*
"""

from apps.users.application.common.ports.transaction_manager import TransactionManager

__all__ = [
    "TransactionManager",
]
