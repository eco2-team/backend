"""UpdateLoginTime command - 로그인 시간 업데이트 UseCase."""

from __future__ import annotations

from datetime import datetime, timezone

from apps.users.application.common.ports.transaction_manager import TransactionManager
from apps.users.application.identity.dto.oauth import UpdateLoginTimeRequest
from apps.users.application.identity.ports.identity_gateway import (
    IdentityCommandGateway,
)


class UpdateLoginTimeCommand:
    """로그인 시간 업데이트 UseCase.

    사용자와 소셜 계정의 last_login_at을 현재 시간으로 업데이트합니다.
    """

    def __init__(
        self,
        command_gateway: IdentityCommandGateway,
        transaction_manager: TransactionManager,
    ) -> None:
        self._command_gateway = command_gateway
        self._transaction_manager = transaction_manager

    async def execute(self, request: UpdateLoginTimeRequest) -> None:
        """로그인 시간을 업데이트합니다.

        Args:
            request: 업데이트 요청
        """
        async with self._transaction_manager.begin():
            await self._command_gateway.update_social_login_time(
                user_id=request.user_id,
                provider=request.provider,
                provider_user_id=request.provider_user_id,
                login_time=datetime.now(timezone.utc),
            )
