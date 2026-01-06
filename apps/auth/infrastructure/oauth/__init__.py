"""OAuth Provider Implementations."""

from apps.auth.infrastructure.oauth.client import OAuthClientImpl
from apps.auth.infrastructure.oauth.providers import (
    GoogleOAuthProvider,
    KakaoOAuthProvider,
    NaverOAuthProvider,
    OAuthProvider,
    OAuthProviderError,
)
from apps.auth.infrastructure.oauth.registry import ProviderRegistry

__all__ = [
    "OAuthProvider",
    "OAuthProviderError",
    "GoogleOAuthProvider",
    "KakaoOAuthProvider",
    "NaverOAuthProvider",
    "ProviderRegistry",
    "OAuthClientImpl",
]
