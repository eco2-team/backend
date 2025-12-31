"""Application ports (interfaces)."""

from apps.users.application.common.ports.social_account_gateway import (
    SocialAccountInfo,
    SocialAccountQueryGateway,
)
from apps.users.application.common.ports.transaction_manager import TransactionManager
from apps.users.application.common.ports.user_character_gateway import (
    UserCharacterQueryGateway,
)
from apps.users.application.common.ports.user_gateway import (
    UserCommandGateway,
    UserQueryGateway,
)

__all__ = [
    "UserQueryGateway",
    "UserCommandGateway",
    "UserCharacterQueryGateway",
    "TransactionManager",
    "SocialAccountQueryGateway",
    "SocialAccountInfo",
]
