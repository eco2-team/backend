"""Naver OAuth Provider."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlencode

from apps.auth.application.common.services.oauth_client import OAuthProfile
from apps.auth.infrastructure.oauth.providers.base import (
    OAuthProvider,
    OAuthProviderError,
)

if TYPE_CHECKING:
    import httpx

NAVER_AUTH_URL = "https://nid.naver.com/oauth2.0/authorize"
NAVER_TOKEN_URL = "https://nid.naver.com/oauth2.0/token"
NAVER_PROFILE_URL = "https://openapi.naver.com/v1/nid/me"


class NaverOAuthProvider(OAuthProvider):
    """Naver OAuth 프로바이더."""

    name = "naver"
    supports_pkce = False

    @property
    def default_scopes(self) -> tuple[str, ...]:
        return ("profile", "email")

    def build_authorization_url(
        self,
        *,
        state: str,
        code_challenge: str | None,
        scope: str | None,
        redirect_uri: str | None,
    ) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri or self.redirect_uri,
            "response_type": "code",
            "state": state,
        }
        scope_values = scope or " ".join(self.default_scopes)
        if scope_values:
            params["scope"] = scope_values
        return f"{NAVER_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(
        self,
        *,
        client: "httpx.AsyncClient",
        code: str,
        code_verifier: str | None,
        redirect_uri: str,
        state: str | None,
    ) -> dict:
        data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
            "state": state,
        }
        response = await client.post(NAVER_TOKEN_URL, data=data)
        response.raise_for_status()
        return response.json()

    async def fetch_profile(
        self,
        *,
        client: "httpx.AsyncClient",
        tokens: dict,
    ) -> OAuthProfile:
        access_token = tokens.get("access_token")
        if not access_token:
            raise OAuthProviderError("Missing Naver access token")
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await client.get(NAVER_PROFILE_URL, headers=headers)
        response.raise_for_status()
        body = response.json()
        response_data = body.get("response") or {}
        return OAuthProfile(
            provider=self.name,
            provider_user_id=response_data.get("id"),
            email=response_data.get("email"),
            nickname=response_data.get("nickname"),
            profile_image_url=response_data.get("profile_image"),
        )
