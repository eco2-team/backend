"""User ports (gateway interfaces)."""

from apps.users.application.user.ports.social_account_gateway import (
    SocialAccountInfo,
    SocialAccountQueryGateway,
)
from apps.users.application.user.ports.user_gateway import (
    UserCommandGateway,
    UserQueryGateway,
)

__all__ = [
    "SocialAccountInfo",
    "SocialAccountQueryGateway",
    "UserCommandGateway",
    "UserQueryGateway",
]
