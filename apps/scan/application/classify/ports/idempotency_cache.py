"""Idempotency Cache Port - 멱등성 캐시 인터페이스."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IdempotencyCache(ABC):
    """멱등성 캐시 Port.

    동일한 요청이 중복 제출되는 것을 방지합니다.
    X-Idempotency-Key 헤더로 클라이언트가 키를 제공합니다.
    """

    @abstractmethod
    async def get(self, key: str) -> dict[str, Any] | None:
        """캐시된 응답 조회.

        Args:
            key: Idempotency key

        Returns:
            캐시된 응답 또는 None
        """
        ...

    @abstractmethod
    async def set(self, key: str, response: dict[str, Any], ttl: int) -> None:
        """응답 캐시 저장.

        Args:
            key: Idempotency key
            response: 캐시할 응답
            ttl: TTL (초)
        """
        ...
