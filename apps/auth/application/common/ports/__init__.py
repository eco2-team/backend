"""Application Ports (Gateway Interfaces).

⚠️ DEPRECATED: 도메인별 분리 완료
새 코드는 도메인별 ports에서 직접 import하세요:
  - apps.auth.application.auth.ports.*
  - apps.auth.application.user.ports.*
  - apps.auth.application.audit.ports.*

이 모듈은 하위 호환성을 위해 re-export만 제공합니다.
"""

# ============================================================================
# 공용 포트 (여기에 유지)
# ============================================================================
from apps.auth.application.common.ports.flusher import Flusher
from apps.auth.application.common.ports.outbox_gateway import OutboxGateway
from apps.auth.application.common.ports.transaction_manager import TransactionManager
from apps.auth.application.common.ports.blacklist_event_publisher import (
    BlacklistEventPublisher,
)

# ============================================================================
# 도메인별 포트 Re-export (하위 호환성)
# ============================================================================
# Auth domain
from apps.auth.application.auth.ports import (
    OAuthProviderGateway,
    OAuthProfile,
    OAuthState,
    OAuthStateStore,
    TokenBlacklistStore,
    TokenIssuer,
    TokenMetadata,
    TokenPair,
    UserTokenStore,
)

# User domain
from apps.auth.application.user.ports import (
    OAuthUserResult,
    SocialAccountGateway,
    UserCommandGateway,
    UserManagementGateway,
    UserQueryGateway,
)

# Audit domain
from apps.auth.application.audit.ports import LoginAuditGateway

# ============================================================================
# Deprecated Aliases (기존 이름 유지)
# ============================================================================
# 기존 코드와 호환을 위한 alias
TokenService = TokenIssuer  # token_service.py → token_issuer.py
StateStore = OAuthStateStore  # state_store.py → oauth_state_store.py
TokenBlacklist = TokenBlacklistStore  # token_blacklist.py → token_blacklist_store.py
UserManagementService = UserManagementGateway  # *_service.py → *_gateway.py
OAuthClientService = OAuthProviderGateway  # oauth_client.py → oauth_provider_gateway.py

__all__ = [
    # 공용 포트
    "Flusher",
    "OutboxGateway",
    "TransactionManager",
    # Auth 포트
    "OAuthProviderGateway",
    "OAuthProfile",
    "OAuthState",
    "OAuthStateStore",
    "TokenBlacklistStore",
    "TokenIssuer",
    "TokenMetadata",
    "TokenPair",
    "UserTokenStore",
    # User 포트
    "OAuthUserResult",
    "SocialAccountGateway",
    "UserCommandGateway",
    "UserManagementGateway",
    "UserQueryGateway",
    # Audit 포트
    "LoginAuditGateway",
    # Deprecated Aliases
    "TokenService",  # → TokenIssuer
    "StateStore",  # → OAuthStateStore
    "TokenBlacklist",  # → TokenBlacklistStore
    "UserManagementService",  # → UserManagementGateway
    "OAuthClientService",  # → OAuthProviderGateway
]
