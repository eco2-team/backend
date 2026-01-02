"""OAuthCallback Command.

OAuth 콜백 처리 Use Case입니다.

Architecture:
    - UseCase(지휘자): OAuthCallbackInteractor
    - Services(연주자): OAuthFlowService(Facade), TokenService(Facade), LoginAuditService(팩토리)
    - Ports(인프라): UsersManagementGateway, LoginAuditGateway, TransactionManager

참고: https://rooftopsnow.tistory.com/127
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apps.auth.application.oauth.dto import (
    OAuthCallbackRequest,
    OAuthCallbackResponse,
)
from apps.auth.application.users.exceptions import UserServiceUnavailableError

if TYPE_CHECKING:
    # Services (연주자)
    from apps.auth.application.audit.services import LoginAuditService
    from apps.auth.application.oauth.services import OAuthFlowService
    from apps.auth.application.token.services import TokenService

    # Ports (인프라)
    from apps.auth.application.audit.ports import LoginAuditGateway
    from apps.auth.application.common.ports import Flusher, TransactionManager
    from apps.auth.application.users.ports import UsersManagementGateway

logger = logging.getLogger(__name__)


class OAuthCallbackInteractor:
    """OAuth 콜백 Interactor (지휘자).

    OAuth 로그인 플로우의 콜백 단계를 오케스트레이션합니다.

    Workflow:
        1. OAuth 인증 플로우 처리 (OAuthFlowService - Facade)
        2. 사용자 조회/생성 (UsersManagementGateway - Port 직접)
        3. 토큰 발급 및 세션 등록 (TokenService - Facade)
        4. 로그인 감사 기록 생성 (LoginAuditService - 팩토리) + 저장 (Gateway - Port 직접)
        5. 트랜잭션 커밋 (TransactionManager - Port 직접)

    Dependencies:
        Services (연주자):
            - oauth_service: OAuth 플로우 Facade (state 검증 + 프로필 조회)
            - token_service: 토큰 Facade (발급 + 세션 관리)
            - audit_service: 감사 엔티티 팩토리 (순수 로직)

        Ports (인프라):
            - user_management: users 도메인 gRPC 통신
            - audit_gateway: 감사 기록 저장
            - flusher: DB 변경사항 플러시
            - transaction_manager: 트랜잭션 제어
    """

    def __init__(
        self,
        # Services (연주자)
        oauth_service: "OAuthFlowService",
        token_service: "TokenService",
        audit_service: "LoginAuditService",
        # Ports (인프라)
        user_management: "UsersManagementGateway",
        audit_gateway: "LoginAuditGateway",
        flusher: "Flusher",
        transaction_manager: "TransactionManager",
    ) -> None:
        # Services
        self._oauth_service = oauth_service
        self._token_service = token_service
        self._audit_service = audit_service
        # Ports
        self._user_management = user_management
        self._audit_gateway = audit_gateway
        self._flusher = flusher
        self._transaction_manager = transaction_manager

    async def execute(self, request: OAuthCallbackRequest) -> OAuthCallbackResponse:
        """OAuth 콜백을 처리합니다.

        Args:
            request: 콜백 요청 DTO

        Returns:
            로그인 결과 응답 DTO

        Raises:
            InvalidStateError: state 검증 실패
            OAuthProviderError: OAuth 프로바이더 오류
            UserServiceUnavailableError: users 도메인 통신 실패
        """
        # 1. OAuth 인증 플로우 (Facade Service에 위임)
        oauth_result = await self._oauth_service.validate_and_fetch_profile(
            provider=request.provider,
            code=request.code,
            state=request.state,
            redirect_uri=request.redirect_uri,
        )
        profile = oauth_result.profile
        state_data = oauth_result.state_data

        # 2. 사용자 조회/생성 (Port 직접 호출 - gRPC)
        user_result = await self._user_management.get_or_create_from_oauth(
            provider=profile.provider,
            provider_user_id=profile.provider_user_id,
            email=profile.email,
            nickname=profile.nickname,
            profile_image_url=profile.profile_image_url,
        )

        if user_result is None:
            logger.error(
                "Failed to get/create user via users service",
                extra={
                    "provider": profile.provider,
                    "provider_user_id": profile.provider_user_id,
                },
            )
            raise UserServiceUnavailableError("Could not communicate with users service")

        user_id = user_result.user_id

        # 3. 토큰 발급 및 세션 등록 (Facade Service에 위임)
        token_result = await self._token_service.issue_and_register(
            user_id=user_id,
            provider=request.provider,
            device_id=state_data.device_id,
            user_agent=request.user_agent,
        )

        # 4. 로그인 감사 기록 (팩토리 Service + Port 직접 호출)
        login_audit = self._audit_service.create_login_audit(
            user_id=user_id,
            provider=request.provider,
            access_jti=token_result.access_jti,
            login_ip=request.ip_address,
            user_agent=request.user_agent,
        )
        self._audit_gateway.add(login_audit)

        # 5. 트랜잭션 커밋 (Port 직접 호출)
        await self._flusher.flush()
        await self._transaction_manager.commit()

        logger.info(
            "OAuth login successful",
            extra={
                "user_id": str(user_id),
                "provider": request.provider,
                "is_new_user": user_result.is_new_user,
            },
        )

        return OAuthCallbackResponse(
            user_id=user_id,
            access_token=token_result.access_token,
            refresh_token=token_result.refresh_token,
            access_expires_at=token_result.access_expires_at,
            refresh_expires_at=token_result.refresh_expires_at,
            frontend_origin=state_data.frontend_origin,
        )
