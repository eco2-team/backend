"""Update profile command - Updates user profile."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from apps.users.application.profile.dto import UserProfile, UserUpdate
from apps.users.application.profile.exceptions import (
    InvalidPhoneNumberError,
    NoChangesProvidedError,
    UserNotFoundError,
)

if TYPE_CHECKING:
    from apps.users.application.common.ports import TransactionManager
    from apps.users.application.identity.ports import SocialAccountQueryGateway
    from apps.users.application.profile.ports import (
        ProfileCommandGateway,
        ProfileQueryGateway,
    )
    from apps.users.application.profile.services import ProfileBuilder
    from apps.users.domain.services import UserService

logger = logging.getLogger(__name__)


class UpdateProfileInteractor:
    """사용자 프로필 업데이트 유스케이스.

    기존 MyService.update_current_user를 대체합니다.
    """

    def __init__(
        self,
        profile_query: "ProfileQueryGateway",
        profile_command: "ProfileCommandGateway",
        social_account_gateway: "SocialAccountQueryGateway",
        transaction_manager: "TransactionManager",
        user_service: "UserService",
        profile_builder: "ProfileBuilder",
    ) -> None:
        self._profile_query = profile_query
        self._profile_command = profile_command
        self._social_account_gateway = social_account_gateway
        self._tx = transaction_manager
        self._user_service = user_service
        self._profile_builder = profile_builder

    async def execute(self, user_id: UUID, update: UserUpdate, provider: str) -> UserProfile:
        """사용자 프로필을 업데이트합니다.

        Args:
            user_id: 사용자 ID (users.users.id)
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
                "user_id": str(user_id),
                "has_nickname": update.nickname is not None,
                "has_phone": update.phone_number is not None,
            },
        )

        if not update.has_changes():
            raise NoChangesProvidedError()

        user = await self._profile_query.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)

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

        updated_user = await self._profile_command.update(user)
        await self._tx.commit()

        # 프로필 DTO 생성
        accounts = await self._social_account_gateway.list_by_user_id(user_id)
        return self._profile_builder.build(updated_user, accounts, provider)
