from __future__ import annotations

from collections.abc import Mapping
from typing import Optional

from domain.auth.core.config import Settings, get_settings
from domain.auth.services.providers.base import OAuthProvider
from domain.auth.services.providers.google import GoogleOAuthProvider
from domain.auth.services.providers.kakao import KakaoOAuthProvider
from domain.auth.services.providers.naver import NaverOAuthProvider


class ProviderRegistry:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.providers: Mapping[str, OAuthProvider] = self._build()

    def _build(self) -> Mapping[str, OAuthProvider]:
        return {
            "kakao": KakaoOAuthProvider(
                client_id=self.settings.kakao_client_id,
                client_secret=self.settings.kakao_client_secret,
                redirect_uri=self._resolve_redirect_uri(self.settings.kakao_redirect_uri, "kakao"),
            ),
            "google": GoogleOAuthProvider(
                client_id=self.settings.google_client_id,
                client_secret=self.settings.google_client_secret,
                redirect_uri=self._resolve_redirect_uri(
                    self.settings.google_redirect_uri, "google"
                ),
            ),
            "naver": NaverOAuthProvider(
                client_id=self.settings.naver_client_id,
                client_secret=self.settings.naver_client_secret,
                redirect_uri=self._resolve_redirect_uri(self.settings.naver_redirect_uri, "naver"),
            ),
        }

    def get(self, provider: str) -> OAuthProvider:
        key = provider.lower()
        if key not in self.providers:
            raise ValueError(f"Unsupported provider: {provider}")
        return self.providers[key]

    def _resolve_redirect_uri(self, override: Optional[str], provider: str) -> Optional[str]:
        if override:
            return str(override)
        template = self.settings.oauth_redirect_template
        if not template:
            return None
        env_value = (self.settings.environment or "").strip() or "dev"
        return template.format(env=env_value, provider=provider)
