"""Redis Streams 기반 이벤트 발행/구독 모듈.

Celery Events 대신 Redis Streams를 사용하여
SSE:RabbitMQ 연결 폭발 문제를 해결합니다.

사용 예시:
    # Worker (동기)
    from domains._shared.events import get_sync_redis_client, publish_stage_event
    redis_client = get_sync_redis_client()
    publish_stage_event(redis_client, job_id, "vision", "started")

    # API (비동기)
    from domains._shared.events import get_async_redis_client, subscribe_events
    redis_client = await get_async_redis_client()
    async for event in subscribe_events(redis_client, job_id):
        yield format_sse(event)
"""

from domains._shared.events.redis_client import (
    get_async_redis_client,
    get_sync_redis_client,
    reset_async_redis_client,
)
from domains._shared.events.redis_streams import (
    STREAM_MAXLEN,
    STREAM_PREFIX,
    STREAM_TTL,
    get_stream_key,
    publish_stage_event,
    subscribe_events,
)

__all__ = [
    "STREAM_PREFIX",
    "STREAM_MAXLEN",
    "STREAM_TTL",
    "get_stream_key",
    "publish_stage_event",
    "subscribe_events",
    "get_sync_redis_client",
    "get_async_redis_client",
    "reset_async_redis_client",
]
