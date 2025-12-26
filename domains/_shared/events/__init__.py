"""Redis Streams 기반 이벤트 발행/구독 모듈.

Celery Events 대신 Redis Streams를 사용하여
SSE:RabbitMQ 연결 폭발 문제를 해결합니다.

v2: SSEBroadcastManager 추가
- 단일 Redis Consumer + Memory Fan-out 패턴
- 연결당 XREAD 대신 중앙 Consumer가 모든 Stream 구독
- 참고: docs/blogs/async/31-sse-fanout-optimization.md

사용 예시:
    # Worker (동기)
    from domains._shared.events import get_sync_redis_client, publish_stage_event
    redis_client = get_sync_redis_client()
    publish_stage_event(redis_client, job_id, "vision", "started")

    # API (비동기) - v1: 직접 구독
    from domains._shared.events import get_async_redis_client, subscribe_events
    redis_client = await get_async_redis_client()
    async for event in subscribe_events(redis_client, job_id):
        yield format_sse(event)

    # API (비동기) - v2: BroadcastManager (권장)
    from domains._shared.events import SSEBroadcastManager
    manager = await SSEBroadcastManager.get_instance()
    async for event in manager.subscribe(job_id):
        yield format_sse(event)
"""

from domains._shared.events.broadcast_manager import SSEBroadcastManager
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
    "SSEBroadcastManager",
]
