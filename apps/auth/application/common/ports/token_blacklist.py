"""TokenBlacklist Port.

토큰 블랙리스트 조회를 위한 Gateway 인터페이스입니다.

Note:
    블랙리스트 추가는 BlacklistEventPublisher를 통해 이벤트로 발행합니다.
    auth_worker가 이벤트를 소비하여 Redis에 저장합니다.
"""

from typing import Protocol


class TokenBlacklist(Protocol):
    """토큰 블랙리스트 조회 인터페이스 (읽기 전용).

    블랙리스트 추가는 BlacklistEventPublisher를 사용하세요.

    구현체:
        - RedisTokenBlacklist (infrastructure/persistence_redis/)
    """

    async def contains(self, jti: str) -> bool:
        """토큰이 블랙리스트에 있는지 확인.

        Args:
            jti: JWT Token ID

        Returns:
            블랙리스트에 있으면 True
        """
        ...
