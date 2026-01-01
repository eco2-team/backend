"""Application ports (gateway interfaces).

⚠️ DEPRECATED: 도메인별 분리 완료
새 코드는 도메인별 ports에서 직접 import하세요:
  - apps.users.application.user.ports.*
  - apps.users.application.character.ports.*

이 모듈은 하위 호환성을 위해 re-export만 제공합니다.
"""

# ============================================================================
# 공용 포트 (여기에 유지)
# ============================================================================
from apps.users.application.common.ports.transaction_manager import TransactionManager

# ============================================================================
# 도메인별 포트 Re-export (하위 호환성)
# ============================================================================
# User domain
from apps.users.application.user.ports import (
    SocialAccountInfo,
    SocialAccountQueryGateway,
    UserCommandGateway,
    UserQueryGateway,
)

# Character domain
from apps.users.application.character.ports import (
    UserCharacterQueryGateway,
)

__all__ = [
    # 공용 포트
    "TransactionManager",
    # User 포트 (하위 호환)
    "UserQueryGateway",
    "UserCommandGateway",
    "SocialAccountQueryGateway",
    "SocialAccountInfo",
    # Character 포트 (하위 호환)
    "UserCharacterQueryGateway",
]
