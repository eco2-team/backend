"""Identity DTO."""

from apps.users.application.identity.dto.oauth import (
    OAuthUserRequest,
    OAuthUserResult,
    UpdateLoginTimeRequest,
)

__all__ = [
    "OAuthUserRequest",
    "OAuthUserResult",
    "UpdateLoginTimeRequest",
]
