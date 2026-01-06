"""Kakao OAuth Provider."""

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

KAKAO_AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_PROFILE_URL = "https://kapi.kakao.com/v2/user/me"


class KakaoOAuthProvider(OAuthProvider):
    """Kakao OAuth 프로바이더."""

    name = "kakao"

    @property
    def default_scopes(self) -> tuple[str, ...]:
        # 카카오는 scope를 사용하지 않고, 개발자 콘솔에서 동의항목을 설정
        return ()

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
        if scope:
            params["scope"] = scope
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        return f"{KAKAO_AUTH_URL}?{urlencode(params)}"

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
            "redirect_uri": redirect_uri,
            "code": code,
        }
        if self.client_secret:
            data["client_secret"] = self.client_secret
        if code_verifier:
            data["code_verifier"] = code_verifier
        response = await client.post(KAKAO_TOKEN_URL, data=data)
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
            raise OAuthProviderError("Missing Kakao access token")
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await client.get(KAKAO_PROFILE_URL, headers=headers)
        response.raise_for_status()
        payload = response.json()

        kakao_account = payload.get("kakao_account") or {}
        profile = kakao_account.get("profile") or {}

        return OAuthProfile(
            provider=self.name,
            provider_user_id=str(payload.get("id")),
            email=kakao_account.get("email"),
            nickname=profile.get("nickname"),
            profile_image_url=profile.get("profile_image_url"),
        )
