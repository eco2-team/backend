"""Event Subscriber Port - Redis Streams 이벤트 구독."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator


class EventSubscriber(ABC):
    """Redis Streams 이벤트 구독 Port.

    레거시 SSE 엔드포인트에서 직접 구독하는 데 사용합니다.
    - POST /classify/completion
    - GET /{task_id}/progress

    메인 흐름에서는 Event Router + SSE Gateway를 사용합니다.
    """

    @abstractmethod
    async def subscribe(
        self,
        job_id: str,
        timeout_sec: int = 120,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """job_id에 해당하는 이벤트 스트림 구독.

        Args:
            job_id: 작업 ID (UUID)
            timeout_sec: 구독 타임아웃 (초)

        Yields:
            이벤트 딕셔너리
            {
                "stage": "vision",
                "status": "completed",
                "progress": 25,
                "result": {...},  # optional
                "type": "keepalive",  # keepalive 이벤트
            }

        Note:
            - keepalive 이벤트는 연결 유지를 위해 주기적으로 전송됩니다.
            - done 이벤트 수신 시 구독이 종료됩니다.
        """
        raise NotImplementedError
        # Generator stub for type checking
        yield {}  # pragma: no cover

    @abstractmethod
    async def get_state(self, job_id: str) -> dict[str, Any] | None:
        """현재 작업 상태 조회 (State KV).

        Args:
            job_id: 작업 ID

        Returns:
            현재 상태 또는 None (작업이 없는 경우)
        """
        raise NotImplementedError
