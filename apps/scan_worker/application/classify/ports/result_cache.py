"""Result Cache Port - 결과 캐싱 추상화."""

from abc import ABC, abstractmethod
from typing import Any


class ResultCachePort(ABC):
    """결과 캐시 포트 - Redis Cache.

    파이프라인 완료 결과를 캐싱하여 /result 엔드포인트에서 조회.
    """

    @abstractmethod
    def cache_result(
        self,
        task_id: str,
        result: dict[str, Any],
        ttl: int | None = None,
    ) -> None:
        """결과를 캐시에 저장.

        Args:
            task_id: 작업 ID (UUID)
            result: 캐싱할 결과 데이터
            ttl: TTL (초), None이면 기본값 사용
        """
        pass

    @abstractmethod
    def get_result(self, task_id: str) -> dict[str, Any] | None:
        """캐시에서 결과 조회.

        Args:
            task_id: 작업 ID (UUID)

        Returns:
            캐싱된 결과 (없으면 None)
        """
        pass
