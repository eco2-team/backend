"""OAuthStateStore Port.

OAuth 인증 플로우의 state 관리를 위한 Gateway 인터페이스입니다.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class OAuthState:
    """OAuth 상태 데이터."""

    provider: str
    redirect_uri: str | None = None
    code_verifier: str | None = None
    device_id: str | None = None
    frontend_origin: str | None = None


class OAuthStateStore(Protocol):
    """OAuth 상태 저장소 인터페이스.

    구현체:
        - RedisStateStore (infrastructure/persistence_redis/)
    """

    async def save(self, state: str, data: OAuthState, ttl_seconds: int = 600) -> None:
        """상태 저장.

        Args:
            state: 상태 키 (랜덤 문자열)
            data: 상태 데이터
            ttl_seconds: TTL (기본 10분)
        """
        ...

    async def consume(self, state: str) -> OAuthState | None:
        """상태 조회 및 삭제 (일회용).

        Args:
            state: 상태 키

        Returns:
            상태 데이터 또는 None (없거나 만료)
        """
        ...
