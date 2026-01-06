"""Google OAuth Provider."""

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

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_PROFILE_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


class GoogleOAuthProvider(OAuthProvider):
    """Google OAuth 프로바이더."""

    name = "google"

    @property
    def default_scopes(self) -> tuple[str, ...]:
        return ("openid", "email", "profile")

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
            "scope": scope or " ".join(self.default_scopes),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
        }
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

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
        }
        if code_verifier:
            data["code_verifier"] = code_verifier
        response = await client.post(GOOGLE_TOKEN_URL, data=data)
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
            raise OAuthProviderError("Missing Google access token")
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await client.get(GOOGLE_PROFILE_URL, headers=headers)
        response.raise_for_status()
        data = response.json()
        return OAuthProfile(
            provider=self.name,
            provider_user_id=data.get("sub"),
            email=data.get("email"),
            nickname=data.get("given_name"),
            profile_image_url=data.get("picture"),
        )
