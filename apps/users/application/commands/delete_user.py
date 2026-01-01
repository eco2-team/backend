"""Delete user command - Deletes user account."""

from __future__ import annotations

import logging
from uuid import UUID

from apps.users.application.common.exceptions import UserNotFoundError
from apps.users.application.common.ports import (
    TransactionManager,
    UserCommandGateway,
    UserQueryGateway,
)

logger = logging.getLogger(__name__)


class DeleteUserInteractor:
    """사용자 삭제 유스케이스.

    기존 MyService.delete_current_user를 대체합니다.

    Note:
        CASCADE 삭제로 user_social_accounts, user_characters도 함께 삭제됩니다.
    """

    def __init__(
        self,
        user_query_gateway: UserQueryGateway,
        user_command_gateway: UserCommandGateway,
        transaction_manager: TransactionManager,
    ) -> None:
        self._user_query = user_query_gateway
        self._user_command = user_command_gateway
        self._tx = transaction_manager

    async def execute(self, user_id: UUID) -> None:
        """사용자 계정을 삭제합니다.

        Args:
            user_id: 사용자 ID (users.users.id)

        Raises:
            UserNotFoundError: 사용자를 찾을 수 없음
        """
        logger.info("User deletion requested", extra={"user_id": str(user_id)})

        user = await self._user_query.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)

        await self._user_command.delete(user_id)
        await self._tx.commit()

        logger.info("User deleted", extra={"user_id": str(user_id)})
