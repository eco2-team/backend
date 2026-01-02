"""OAuthAuthorize Command.

OAuth 인증 URL 생성 Use Case입니다.

Architecture:
    - UseCase(지휘자): OAuthAuthorizeInteractor
    - Services(연주자): OAuthFlowService
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from apps.auth.application.oauth.dto import (
    OAuthAuthorizeRequest,
    OAuthAuthorizeResponse,
)

if TYPE_CHECKING:
    from apps.auth.application.oauth.services import OAuthFlowService


class OAuthAuthorizeInteractor:
    """OAuth 인증 URL 생성 Interactor (지휘자).

    OAuth 로그인 플로우의 첫 단계를 오케스트레이션합니다.

    Workflow:
        1. 랜덤 state 생성 (CSRF 방지)
        2. PKCE code_verifier 생성 (보안 강화)
        3. state 데이터 저장 (OAuthFlowService)
        4. 인증 URL 반환 (OAuthFlowService)

    Dependencies:
        Services (연주자):
            - oauth_service: OAuth state 저장 및 URL 생성
    """

    def __init__(self, oauth_service: "OAuthFlowService") -> None:
        self._oauth_service = oauth_service

    async def execute(self, request: OAuthAuthorizeRequest) -> OAuthAuthorizeResponse:
        """OAuth 인증 URL을 생성합니다.

        Args:
            request: 인증 요청 DTO

        Returns:
            인증 URL과 state를 담은 응답 DTO
        """
        # 1. state 생성 (CSRF 방지)
        state = request.state or secrets.token_urlsafe(32)

        # 2. PKCE code_verifier 생성
        code_verifier = secrets.token_urlsafe(64)

        # 3. state 데이터 저장 (Service에 위임)
        await self._oauth_service.save_state(
            state,
            provider=request.provider,
            redirect_uri=request.redirect_uri,
            code_verifier=code_verifier,
            device_id=request.device_id,
            frontend_origin=request.frontend_origin,
        )

        # 4. 인증 URL 생성 (Service에 위임)
        authorization_url = self._oauth_service.get_authorization_url(
            request.provider,
            redirect_uri=request.redirect_uri or "",
            state=state,
            code_verifier=code_verifier,
        )

        return OAuthAuthorizeResponse(
            authorization_url=authorization_url,
            state=state,
        )
