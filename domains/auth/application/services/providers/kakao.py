from __future__ import annotations

from urllib.parse import urlencode
from typing import Optional

import httpx

from domains.auth.application.schemas.oauth import OAuthProfile
from domains.auth.application.services.providers.base import OAuthProvider, OAuthProviderError

KAKAO_AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_PROFILE_URL = "https://kapi.kakao.com/v2/user/me"


class KakaoOAuthProvider(OAuthProvider):
    name = "kakao"

    @property
    def default_scopes(self) -> tuple[str, ...]:
        # 카카오는 scope를 사용하지 않고, 개발자 콘솔에서 동의항목을 설정
        return ()

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
        # 카카오는 scope를 보내지 않음 (동의항목은 카카오 개발자 콘솔에서 설정)
        # scope 파라미터를 명시적으로 전달한 경우에만 추가
        if scope:
            params["scope"] = scope
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        return f"{KAKAO_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(
        self,
        *,
        client: httpx.AsyncClient,
        code: str,
        code_verifier: Optional[str],
        redirect_uri: str,
        state: Optional[str],
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
        client: httpx.AsyncClient,
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
        phone_number = kakao_account.get("phone_number")

        return OAuthProfile(
            provider=self.name,
            provider_user_id=str(payload.get("id")),
            email=kakao_account.get("email"),
            nickname=profile.get("nickname"),
            name=profile.get("nickname"),
            profile_image_url=profile.get("profile_image_url"),
            phone_number=phone_number,
        )
