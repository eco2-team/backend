"""OAuth Client Implementation.

OAuthClientService 포트의 구현체입니다.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import TYPE_CHECKING

import httpx

from apps.auth.application.common.services.oauth_client import OAuthProfile
from apps.auth.application.oauth.exceptions import OAuthProviderError

if TYPE_CHECKING:
    from apps.auth.infrastructure.oauth.registry import ProviderRegistry

logger = logging.getLogger(__name__)


class OAuthClientImpl:
    """OAuth 클라이언트 구현체.

    OAuthClientService 구현체.
    """

    def __init__(self, registry: "ProviderRegistry", timeout_seconds: float) -> None:
        """
        Args:
            registry: OAuth 프로바이더 레지스트리
            timeout_seconds: HTTP 클라이언트 타임아웃 (설정에서 주입)
        """
        self._registry = registry
        self._timeout = timeout_seconds

    def _compute_code_challenge(self, code_verifier: str) -> str:
        """PKCE code_challenge 생성 (S256)."""
        digest = hashlib.sha256(code_verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    def get_authorization_url(
        self,
        provider: str,
        *,
        redirect_uri: str,
        state: str,
        code_verifier: str | None = None,
    ) -> str:
        """인증 URL 생성."""
        oauth_provider = self._registry.get(provider)

        code_challenge = None
        if code_verifier and oauth_provider.supports_pkce:
            code_challenge = self._compute_code_challenge(code_verifier)

        return oauth_provider.build_authorization_url(
            state=state,
            code_challenge=code_challenge,
            scope=None,
            redirect_uri=redirect_uri or oauth_provider.redirect_uri,
        )

    async def fetch_profile(
        self,
        provider: str,
        *,
        code: str,
        redirect_uri: str,
        state: str,
        code_verifier: str | None = None,
    ) -> OAuthProfile:
        """OAuth 토큰 교환 및 프로필 조회."""
        oauth_provider = self._registry.get(provider)

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                # 토큰 교환
                tokens = await oauth_provider.exchange_code(
                    client=client,
                    code=code,
                    code_verifier=code_verifier if oauth_provider.supports_pkce else None,
                    redirect_uri=redirect_uri,
                    state=state,
                )

                # 프로필 조회
                profile = await oauth_provider.fetch_profile(
                    client=client,
                    tokens=tokens,
                )

                return profile

        except httpx.HTTPStatusError as e:
            logger.warning(f"OAuth API error: {e.response.status_code}")
            raise OAuthProviderError(provider, f"API error: {e.response.status_code}") from e
        except httpx.HTTPError as e:
            logger.warning(f"OAuth request failed: {e}")
            raise OAuthProviderError(provider, str(e)) from e
