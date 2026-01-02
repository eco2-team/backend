"""BlacklistEventPublisher Port.

블랙리스트 이벤트 발행을 위한 인터페이스입니다.
"""

from __future__ import annotations

from typing import Protocol

from apps.auth.domain.value_objects.token_payload import TokenPayload


class BlacklistEventPublisher(Protocol):
    """블랙리스트 이벤트 발행 인터페이스.

    로그아웃 시 블랙리스트 이벤트를 메시지 큐로 발행합니다.
    auth_worker가 이벤트를 소비하여 Redis에 저장합니다.

    구현체:
        - RabbitMQBlacklistEventPublisher (infrastructure/messaging/)
    """

    async def publish_add(
        self,
        payload: TokenPayload,
        reason: str = "logout",
    ) -> None:
        """블랙리스트 추가 이벤트 발행.

        Args:
            payload: 토큰 페이로드
            reason: 블랙리스트 사유 (logout, token_rotated 등)
        """
        ...

    async def publish_remove(self, jti: str) -> None:
        """블랙리스트 제거 이벤트 발행.

        Args:
            jti: JWT Token ID
        """
        ...
