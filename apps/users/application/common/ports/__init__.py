"""Application ports (gateway interfaces).

⚠️ DEPRECATED: 도메인별 분리 완료
새 코드는 도메인별 ports에서 직접 import하세요:
  - apps.users.application.profile.ports.*
  - apps.users.application.identity.ports.*
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
# Profile domain
from apps.users.application.profile.ports import (
    ProfileCommandGateway,
    ProfileQueryGateway,
)

# Identity domain
from apps.users.application.identity.ports import (
    SocialAccountInfo,
    SocialAccountQueryGateway,
)

# Character domain
from apps.users.application.character.ports import (
    UserCharacterQueryGateway,
)

# ============================================================================
# Deprecated Aliases (기존 이름 유지)
# ============================================================================
UserQueryGateway = ProfileQueryGateway  # user_gateway.py → profile/ports/profile_gateway.py
UserCommandGateway = ProfileCommandGateway

__all__ = [
    # 공용 포트
    "TransactionManager",
    # Profile 포트
    "ProfileQueryGateway",
    "ProfileCommandGateway",
    # Identity 포트
    "SocialAccountQueryGateway",
    "SocialAccountInfo",
    # Character 포트
    "UserCharacterQueryGateway",
    # Deprecated Aliases
    "UserQueryGateway",  # → ProfileQueryGateway
    "UserCommandGateway",  # → ProfileCommandGateway
]
