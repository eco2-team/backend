"""Update profile command - Updates user profile."""

from __future__ import annotations

import logging
from uuid import UUID

from apps.users.application.common.dto import UserProfile, UserUpdate
from apps.users.application.common.exceptions import (
    InvalidPhoneNumberError,
    NoChangesProvidedError,
    UserNotFoundError,
)
from apps.users.application.common.ports import (
    SocialAccountQueryGateway,
    TransactionManager,
    UserCommandGateway,
    UserQueryGateway,
)
from apps.users.application.common.services import ProfileBuilder
from apps.users.domain.services import UserService

logger = logging.getLogger(__name__)


class UpdateProfileInteractor:
    """사용자 프로필 업데이트 유스케이스.

    기존 MyService.update_current_user를 대체합니다.
    """

    def __init__(
        self,
        user_query_gateway: UserQueryGateway,
        user_command_gateway: UserCommandGateway,
        social_account_gateway: SocialAccountQueryGateway,
        transaction_manager: TransactionManager,
        user_service: UserService,
        profile_builder: ProfileBuilder,
    ) -> None:
        self._user_query = user_query_gateway
        self._user_command = user_command_gateway
        self._social_account_gateway = social_account_gateway
        self._tx = transaction_manager
        self._user_service = user_service
        self._profile_builder = profile_builder

    async def execute(
        self, auth_user_id: UUID, update: UserUpdate, provider: str
    ) -> UserProfile:
        """사용자 프로필을 업데이트합니다.

        Args:
            auth_user_id: 인증 사용자 ID
            update: 업데이트할 정보
            provider: 현재 로그인 프로바이더

        Returns:
            업데이트된 UserProfile

        Raises:
            UserNotFoundError: 사용자를 찾을 수 없음
            NoChangesProvidedError: 변경사항 없음
            InvalidPhoneNumberError: 전화번호 형식 오류
        """
        logger.info(
            "Profile update requested",
            extra={
                "user_id": str(auth_user_id),
                "has_nickname": update.nickname is not None,
                "has_phone": update.phone_number is not None,
            },
        )

        if not update.has_changes():
            raise NoChangesProvidedError()

        user = await self._user_query.get_by_auth_user_id(auth_user_id)
        if user is None:
            raise UserNotFoundError()

        # 전화번호 유효성 검사 및 정규화
        normalized_phone = None
        if update.phone_number is not None:
            result = self._user_service.validate_and_normalize_phone(update.phone_number)
            if not result.is_valid:
                raise InvalidPhoneNumberError(result.error or "Invalid phone number")
            normalized_phone = result.normalized

        # 프로필 업데이트
        user.update_profile(
            nickname=update.nickname,
            phone_number=normalized_phone,
        )

        updated_user = await self._user_command.update(user)
        await self._tx.commit()

        # 프로필 DTO 생성
        accounts = await self._social_account_gateway.list_by_user_id(auth_user_id)
        return self._profile_builder.build(updated_user, accounts, provider)
