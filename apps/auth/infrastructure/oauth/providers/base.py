"""OAuth Provider Base Class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

    from apps.auth.application.common.services.oauth_client import OAuthProfile


class OAuthProviderError(RuntimeError):
    """OAuth 프로바이더 오류."""

    pass


class OAuthProvider(ABC):
    """OAuth 프로바이더 추상 클래스."""

    name: str
    supports_pkce: bool = True

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str | None,
        redirect_uri: str | None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    @property
    def default_scopes(self) -> tuple[str, ...]:
        """기본 스코프."""
        return ()

    @abstractmethod
    def build_authorization_url(
        self,
        *,
        state: str,
        code_challenge: str | None,
        scope: str | None,
        redirect_uri: str | None,
    ) -> str:
        """인증 URL 생성."""
        raise NotImplementedError

    @abstractmethod
    async def exchange_code(
        self,
        *,
        client: "httpx.AsyncClient",
        code: str,
        code_verifier: str | None,
        redirect_uri: str,
        state: str | None,
    ) -> dict:
        """인증 코드로 토큰 교환."""
        raise NotImplementedError

    @abstractmethod
    async def fetch_profile(
        self,
        *,
        client: "httpx.AsyncClient",
        tokens: dict,
    ) -> "OAuthProfile":
        """사용자 프로필 조회."""
        raise NotImplementedError
