"""TokenBlacklistStore Port.

토큰 블랙리스트 관리를 위한 Gateway 인터페이스입니다.
"""

from typing import Protocol

from apps.auth.domain.value_objects.token_payload import TokenPayload


class TokenBlacklistStore(Protocol):
    """토큰 블랙리스트 저장소 인터페이스.

    구현체:
        - RedisTokenBlacklist (infrastructure/persistence_redis/)
    """

    async def add(self, payload: TokenPayload, reason: str = "revoked") -> None:
        """토큰을 블랙리스트에 추가.

        Args:
            payload: 토큰 페이로드
            reason: 블랙리스트 사유 (logout, token_rotated 등)
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
