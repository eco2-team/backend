"""Users domain ports.

사용자 관련 CRUD 및 외부 users 도메인 통신 포트입니다.
"""

from apps.auth.application.users.ports.user_management_gateway import (
    OAuthUserResult,
    UserManagementGateway,
)
from apps.auth.application.users.ports.user_query_gateway import UserQueryGateway
from apps.auth.application.users.ports.user_command_gateway import UserCommandGateway
from apps.auth.application.users.ports.social_account_gateway import SocialAccountGateway

__all__ = [
    "UserManagementGateway",
    "UserQueryGateway",
    "UserCommandGateway",
    "SocialAccountGateway",
    "OAuthUserResult",
]
