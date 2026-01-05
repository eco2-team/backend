"""Result Cache Port - 결과 캐시 저장/조회."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ResultCache(ABC):
    """결과 캐시 Port.

    파이프라인 완료 결과를 Cache Redis에 저장하고 조회합니다.
    """

    @abstractmethod
    async def get(self, job_id: str) -> dict[str, Any] | None:
        """결과 조회.

        Args:
            job_id: 작업 ID (UUID)

        Returns:
            캐시된 결과 또는 None
        """
        raise NotImplementedError

    @abstractmethod
    def set_sync(
        self,
        job_id: str,
        result: dict[str, Any],
        ttl_seconds: int = 3600,
    ) -> None:
        """결과 저장 (동기 버전, Celery Worker용).

        Args:
            job_id: 작업 ID (UUID)
            result: 저장할 결과
            ttl_seconds: TTL (초, 기본 1시간)

        Note:
            gevent pool에서는 블로킹 I/O가 자동으로 greenlet 전환됩니다.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_state(self, job_id: str) -> dict[str, Any] | None:
        """현재 작업 상태 조회 (State KV).

        결과가 아직 없을 때 현재 처리 단계를 확인하는 용도입니다.

        Args:
            job_id: 작업 ID

        Returns:
            상태 정보 또는 None
        """
        raise NotImplementedError
