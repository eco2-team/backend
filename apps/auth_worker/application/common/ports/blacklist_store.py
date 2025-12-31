"""Blacklist Store Port.

블랙리스트 저장소 인터페이스입니다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class BlacklistStore(Protocol):
    """블랙리스트 저장소 인터페이스.

    구현체:
        - RedisBlacklistStore (infrastructure/persistence_redis/)
    """

    async def add(
        self,
        jti: str,
        expires_at: datetime,
        *,
        user_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        """토큰을 블랙리스트에 추가.

        Args:
            jti: JWT Token ID
            expires_at: 토큰 만료 시간 (TTL 계산용)
            user_id: 사용자 ID (로깅용)
            reason: 블랙리스트 사유
        """
        ...

    async def contains(self, jti: str) -> bool:
        """토큰이 블랙리스트에 있는지 확인.

        Args:
            jti: JWT Token ID

        Returns:
            블랙리스트에 있으면 True
        """
        ...

    async def remove(self, jti: str) -> None:
        """토큰을 블랙리스트에서 제거.

        Args:
            jti: JWT Token ID
        """
        ...
