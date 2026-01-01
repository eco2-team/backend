"""UserTokenStore Port.

사용자별 토큰 세션 관리를 위한 Gateway 인터페이스입니다.
"""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass
class TokenMetadata:
    """토큰 메타데이터."""

    device_id: str | None = None
    user_agent: str | None = None


class UserTokenStore(Protocol):
    """사용자 토큰 저장소 인터페이스.

    구현체:
        - RedisUserTokenStore (infrastructure/persistence_redis/)
    """

    async def register(
        self,
        *,
        user_id: UUID,
        jti: str,
        issued_at: int,
        expires_at: int,
        device_id: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """토큰 등록.

        Args:
            user_id: 사용자 ID
            jti: JWT Token ID
            issued_at: 발급 시각 (Unix timestamp)
            expires_at: 만료 시각 (Unix timestamp)
            device_id: 기기 ID (선택)
            user_agent: User-Agent (선택)
        """
        ...

    async def contains(self, user_id: UUID, jti: str) -> bool:
        """토큰 존재 여부 확인.

        Args:
            user_id: 사용자 ID
            jti: JWT Token ID

        Returns:
            존재하면 True
        """
        ...

    async def remove(self, user_id: UUID, jti: str) -> None:
        """토큰 제거.

        Args:
            user_id: 사용자 ID
            jti: JWT Token ID
        """
        ...

    async def get_metadata(self, jti: str) -> TokenMetadata | None:
        """토큰 메타데이터 조회.

        Args:
            jti: JWT Token ID

        Returns:
            메타데이터 또는 None
        """
        ...
