"""Event Subscriber Redis Adapter - Redis Streams 이벤트 구독."""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

from apps.scan.application.classify.ports.event_subscriber import EventSubscriber

logger = logging.getLogger(__name__)


class EventSubscriberRedis(EventSubscriber):
    """Redis Streams 이벤트 구독 Adapter.

    레거시 SSE 엔드포인트에서 직접 구독하는 데 사용합니다:
    - POST /classify/completion
    - GET /{task_id}/progress

    기존 subscribe_events 함수를 래핑하여 정합성을 유지합니다.
    """

    def __init__(self, redis_url: str | None = None):
        """초기화.

        Args:
            redis_url: Redis URL (None이면 환경변수에서 가져옴)
        """
        self._redis_url = redis_url

    async def subscribe(
        self,
        job_id: str,
        timeout_sec: int = 120,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """job_id에 해당하는 이벤트 스트림 구독.

        기존 subscribe_events 함수를 사용하여 정합성 유지.
        """
        from domains._shared.events import (
            get_async_redis_client,
            subscribe_events as _subscribe_events,
        )

        redis_client = await get_async_redis_client()

        async for event in _subscribe_events(redis_client, job_id):
            yield event

            # done 이벤트 수신 시 종료
            if event.get("stage") == "done":
                break

    async def get_state(self, job_id: str) -> dict[str, Any] | None:
        """현재 작업 상태 조회 (State KV).

        scan:state:{job_id} 키에서 현재 상태를 조회합니다.
        """
        import json

        from domains._shared.events import get_async_redis_client

        redis_client = await get_async_redis_client()
        state_key = f"scan:state:{job_id}"

        try:
            data = await redis_client.get(state_key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(
                "state_kv_read_failed",
                extra={"job_id": job_id, "error": str(e)},
            )

        return None
