"""GetOrCreateFromOAuth command - OAuth 로그인 시 사용자 조회/생성 UseCase."""

from __future__ import annotations

from uuid import uuid4

from apps.users.application.common.ports.transaction_manager import TransactionManager
from apps.users.application.identity.dto.oauth import OAuthUserRequest, OAuthUserResult
from apps.users.application.identity.ports.identity_gateway import (
    IdentityCommandGateway,
    IdentityQueryGateway,
)


class GetOrCreateFromOAuthCommand:
    """OAuth 로그인 시 사용자 조회/생성 UseCase.

    provider + provider_user_id로 기존 사용자를 조회하고,
    없으면 새 사용자와 소셜 계정을 생성합니다.
    """

    def __init__(
        self,
        query_gateway: IdentityQueryGateway,
        command_gateway: IdentityCommandGateway,
        transaction_manager: TransactionManager,
    ) -> None:
        self._query_gateway = query_gateway
        self._command_gateway = command_gateway
        self._transaction_manager = transaction_manager

    async def execute(self, request: OAuthUserRequest) -> OAuthUserResult:
        """OAuth 로그인을 처리합니다.

        Args:
            request: OAuth 사용자 정보

        Returns:
            사용자 정보 + 소셜 계정 정보 + 신규 여부
        """
        async with self._transaction_manager.begin():
            # 1. 기존 사용자 조회
            existing = await self._query_gateway.get_by_provider_identity(
                provider=request.provider,
                provider_user_id=request.provider_user_id,
            )

            if existing:
                # 기존 사용자 반환
                user = existing.user
                social = existing.social_account
                return OAuthUserResult(
                    user_id=user.id,
                    nickname=user.nickname,
                    email=user.email,
                    phone_number=user.phone_number,
                    profile_image_url=user.profile_image_url,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                    last_login_at=user.last_login_at,
                    is_new_user=False,
                    social_account_id=social.id,
                    provider=social.provider,
                    provider_user_id=social.provider_user_id,
                    social_email=social.email,
                    social_last_login_at=social.last_login_at,
                )

            # 2. 신규 사용자 + 소셜 계정 생성
            user_id = uuid4()
            result = await self._command_gateway.create_user_with_social_account(
                user_id=user_id,
                provider=request.provider,
                provider_user_id=request.provider_user_id,
                email=request.email,
                nickname=request.nickname,
                profile_image_url=request.profile_image_url,
            )

            user = result.user
            social = result.social_account
            return OAuthUserResult(
                user_id=user.id,
                nickname=user.nickname,
                email=user.email,
                phone_number=user.phone_number,
                profile_image_url=user.profile_image_url,
                created_at=user.created_at,
                updated_at=user.updated_at,
                last_login_at=user.last_login_at,
                is_new_user=True,
                social_account_id=social.id,
                provider=social.provider,
                provider_user_id=social.provider_user_id,
                social_email=social.email,
                social_last_login_at=social.last_login_at,
            )
