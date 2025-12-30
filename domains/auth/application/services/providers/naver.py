from __future__ import annotations

from urllib.parse import urlencode
from typing import Optional

import httpx

from domains.auth.application.schemas.oauth import OAuthProfile
from domains.auth.application.services.providers.base import OAuthProvider, OAuthProviderError

NAVER_AUTH_URL = "https://nid.naver.com/oauth2.0/authorize"
NAVER_TOKEN_URL = "https://nid.naver.com/oauth2.0/token"
NAVER_PROFILE_URL = "https://openapi.naver.com/v1/nid/me"


class NaverOAuthProvider(OAuthProvider):
    name = "naver"
    supports_pkce = False

    @property
    def default_scopes(self) -> tuple[str, ...]:
        return ("profile", "email")

    def build_authorization_url(
        self,
        *,
        state: str,
        code_challenge: Optional[str],
        scope: Optional[str],
        redirect_uri: Optional[str],
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
        client: httpx.AsyncClient,
        code: str,
        code_verifier: Optional[str],
        redirect_uri: str,
        state: Optional[str],
    ) -> dict:
        # RFC 6749: application/x-www-form-urlencoded 바디로 전송
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
        client: httpx.AsyncClient,
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
        phone_number = response_data.get("mobile_e164") or response_data.get("mobile")
        return OAuthProfile(
            provider=self.name,
            provider_user_id=response_data.get("id"),
            email=response_data.get("email"),
            nickname=response_data.get("nickname"),
            name=response_data.get("name"),
            profile_image_url=response_data.get("profile_image"),
            phone_number=phone_number,
        )
