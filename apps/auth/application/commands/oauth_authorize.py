"""OAuthAuthorize Command.

OAuth 인증 URL 생성 Use Case입니다.
"""

from __future__ import annotations

import secrets

from apps.auth.application.common.dto.auth import (
    OAuthAuthorizeRequest,
    OAuthAuthorizeResponse,
)

# OAuth 도메인 포트
from apps.auth.application.oauth.ports import (
    OAuthProviderGateway,
    OAuthState,
    OAuthStateStore,
)


class OAuthAuthorizeInteractor:
    """OAuth 인증 URL 생성 Interactor.

    OAuth 로그인 플로우의 첫 단계:
    1. 랜덤 state 생성 (CSRF 방지)
    2. PKCE code_verifier 생성 (보안 강화)
    3. state 데이터 저장
    4. 인증 URL 반환
    """

    def __init__(
        self,
        oauth_state_store: OAuthStateStore,
        oauth_provider: OAuthProviderGateway,
    ) -> None:
        self._oauth_state_store = oauth_state_store
        self._oauth_provider = oauth_provider

    async def execute(self, request: OAuthAuthorizeRequest) -> OAuthAuthorizeResponse:
        """OAuth 인증 URL 생성.

        Args:
            request: 인증 요청 DTO

        Returns:
            인증 URL과 state를 담은 응답 DTO
        """
        # 1. state 생성 (CSRF 방지)
        state = request.state or secrets.token_urlsafe(32)

        # 2. PKCE code_verifier 생성
        code_verifier = secrets.token_urlsafe(64)

        # 3. state 데이터 저장
        oauth_state = OAuthState(
            provider=request.provider,
            redirect_uri=request.redirect_uri,
            code_verifier=code_verifier,
            device_id=request.device_id,
            frontend_origin=request.frontend_origin,
        )
        await self._oauth_state_store.save(state, oauth_state, ttl_seconds=600)

        # 4. 인증 URL 생성
        authorization_url = self._oauth_provider.get_authorization_url(
            request.provider,
            redirect_uri=request.redirect_uri or "",
            state=state,
            code_verifier=code_verifier,
        )

        return OAuthAuthorizeResponse(
            authorization_url=authorization_url,
            state=state,
        )
