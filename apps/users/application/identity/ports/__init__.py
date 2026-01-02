"""Identity ports."""

from apps.users.application.identity.ports.identity_gateway import (
    IdentityCommandGateway,
    IdentityQueryGateway,
)
from apps.users.application.identity.ports.social_account_gateway import (
    SocialAccountInfo,
    SocialAccountQueryGateway,
)

__all__ = [
    "IdentityCommandGateway",
    "IdentityQueryGateway",
    "SocialAccountInfo",
    "SocialAccountQueryGateway",
]
