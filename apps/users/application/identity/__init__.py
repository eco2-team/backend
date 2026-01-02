"""Identity feature module.

OAuth 로그인 관련 사용자 식별/생성 기능을 제공합니다.
"""

from apps.users.application.identity.commands import (
    GetOrCreateFromOAuthCommand,
    UpdateLoginTimeCommand,
)
from apps.users.application.identity.dto import (
    OAuthUserRequest,
    OAuthUserResult,
    UpdateLoginTimeRequest,
)
from apps.users.application.identity.ports import (
    IdentityCommandGateway,
    IdentityQueryGateway,
)
from apps.users.application.identity.queries import GetUserQuery

__all__ = [
    # Commands
    "GetOrCreateFromOAuthCommand",
    "UpdateLoginTimeCommand",
    # Queries
    "GetUserQuery",
    # DTOs
    "OAuthUserRequest",
    "OAuthUserResult",
    "UpdateLoginTimeRequest",
    # Ports
    "IdentityCommandGateway",
    "IdentityQueryGateway",
]
