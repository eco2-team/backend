"""OAuthProviderGateway Port.

OAuth 프로바이더(Google, Kakao, Naver 등)와의 통신을 담당하는 Gateway 인터페이스입니다.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class OAuthProfile:
    """OAuth 프로필 데이터."""

    provider: str
    provider_user_id: str
    email: str | None = None
    nickname: str | None = None
    profile_image_url: str | None = None


@dataclass
class OAuthTokens:
    """OAuth 토큰 데이터."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int | None = None


class OAuthProviderGateway(Protocol):
    """OAuth 프로바이더 Gateway 인터페이스.

    구현체:
        - OAuthClientImpl (infrastructure/oauth/)
    """

    def get_authorization_url(
        self,
        provider: str,
        *,
        redirect_uri: str,
        state: str,
        code_verifier: str | None = None,
    ) -> str:
        """인증 URL 생성.

        Args:
            provider: OAuth 프로바이더
            redirect_uri: 콜백 URL
            state: CSRF 방지용 상태 값
            code_verifier: PKCE 코드 검증자 (선택)

        Returns:
            인증 URL
        """
        ...

    async def fetch_profile(
        self,
        provider: str,
        *,
        code: str,
        redirect_uri: str,
        state: str,
        code_verifier: str | None = None,
    ) -> OAuthProfile:
        """OAuth 토큰 교환 및 프로필 조회.

        Args:
            provider: OAuth 프로바이더
            code: 인증 코드
            redirect_uri: 콜백 URL
            state: 상태 값
            code_verifier: PKCE 코드 검증자 (선택)

        Returns:
            사용자 프로필

        Raises:
            OAuthProviderError: 프로바이더 오류
        """
        ...
