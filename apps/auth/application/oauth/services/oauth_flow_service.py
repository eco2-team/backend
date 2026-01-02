"""OAuthFlowService - OAuth 인증 플로우 서비스.

"연주자" 역할: OAuth state 검증 및 프로필 조회를 담당합니다.
UseCase(지휘자)가 이 서비스를 호출하여 OAuth 관련 작업을 위임합니다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from apps.auth.application.oauth.exceptions import (
    InvalidStateError,
    OAuthProviderError,
)

if TYPE_CHECKING:
    from apps.auth.application.oauth.ports import (
        OAuthProfile,
        OAuthProviderGateway,
        OAuthState,
        OAuthStateStore,
    )

logger = logging.getLogger(__name__)


@dataclass
class OAuthFlowResult:
    """OAuth 플로우 결과."""

    profile: "OAuthProfile"
    state_data: "OAuthState"


class OAuthFlowService:
    """OAuth 인증 플로우 서비스.

    Responsibilities:
        - state 검증 (CSRF 방지)
        - OAuth 프로바이더와 통신하여 프로필 조회
        - 인증 URL 생성

    Collaborators:
        - OAuthStateStore: state 저장/조회
        - OAuthProviderGateway: OAuth 프로바이더 통신
    """

    def __init__(
        self,
        state_store: "OAuthStateStore",
        provider_gateway: "OAuthProviderGateway",
    ) -> None:
        self._state_store = state_store
        self._provider_gateway = provider_gateway

    async def validate_and_fetch_profile(
        self,
        *,
        provider: str,
        code: str,
        state: str,
        redirect_uri: str | None = None,
    ) -> OAuthFlowResult:
        """State 검증 후 OAuth 프로필을 조회합니다.

        Args:
            provider: OAuth 프로바이더
            code: 인증 코드
            state: CSRF state 값
            redirect_uri: 콜백 URL (선택, state에서 복원 가능)

        Returns:
            OAuthFlowResult: 프로필 및 state 데이터

        Raises:
            InvalidStateError: state 검증 실패
            OAuthProviderError: OAuth 프로바이더 오류
        """
        # 1. State 검증 및 소비 (일회용)
        state_data = await self._state_store.consume(state)
        if state_data is None:
            logger.warning("Invalid or expired OAuth state", extra={"state": state[:8]})
            raise InvalidStateError("Invalid or expired state")

        if state_data.provider != provider:
            logger.warning(
                "State provider mismatch",
                extra={
                    "expected": state_data.provider,
                    "actual": provider,
                },
            )
            raise InvalidStateError("State provider mismatch")

        # 2. Redirect URI 결정 (요청 > state 저장값)
        final_redirect_uri = redirect_uri or state_data.redirect_uri or ""

        # 3. OAuth 프로필 조회
        try:
            profile = await self._provider_gateway.fetch_profile(
                provider,
                code=code,
                redirect_uri=final_redirect_uri,
                state=state,
                code_verifier=state_data.code_verifier,
            )
        except Exception as e:
            logger.warning(
                "OAuth profile fetch failed",
                extra={"provider": provider, "error": str(e)},
            )
            raise OAuthProviderError(provider, str(e)) from e

        logger.info(
            "OAuth profile fetched successfully",
            extra={
                "provider": provider,
                "provider_user_id": profile.provider_user_id,
            },
        )

        return OAuthFlowResult(profile=profile, state_data=state_data)

    def get_authorization_url(
        self,
        provider: str,
        *,
        redirect_uri: str,
        state: str,
        code_verifier: str | None = None,
    ) -> str:
        """OAuth 인증 URL을 생성합니다.

        Args:
            provider: OAuth 프로바이더
            redirect_uri: 콜백 URL
            state: CSRF state 값
            code_verifier: PKCE 코드 검증자 (선택)

        Returns:
            인증 URL
        """
        return self._provider_gateway.get_authorization_url(
            provider,
            redirect_uri=redirect_uri,
            state=state,
            code_verifier=code_verifier,
        )

    async def save_state(
        self,
        state: str,
        *,
        provider: str,
        redirect_uri: str | None = None,
        code_verifier: str | None = None,
        device_id: str | None = None,
        frontend_origin: str | None = None,
        ttl_seconds: int = 600,
    ) -> None:
        """OAuth state를 저장합니다.

        Args:
            state: state 키
            provider: OAuth 프로바이더
            redirect_uri: 콜백 URL
            code_verifier: PKCE 코드 검증자
            device_id: 기기 ID
            frontend_origin: 프론트엔드 origin
            ttl_seconds: TTL (기본 10분)
        """
        from apps.auth.application.oauth.ports import OAuthState

        state_data = OAuthState(
            provider=provider,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            device_id=device_id,
            frontend_origin=frontend_origin,
        )
        await self._state_store.save(state, state_data, ttl_seconds)
