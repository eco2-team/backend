"""OAuth domain exceptions."""

from apps.auth.application.oauth.exceptions.oauth import (
    InvalidStateError,
    OAuthProviderError,
)

__all__ = [
    "InvalidStateError",
    "OAuthProviderError",
]
