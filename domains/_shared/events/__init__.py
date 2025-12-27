"""Redis Streams 기반 이벤트 발행 모듈.

Event Router + Pub/Sub 아키텍처:
- Worker는 Redis Streams에 이벤트 발행 (멱등성 보장)
- Event Router가 Streams를 소비하여 Pub/Sub로 발행
- SSE-Gateway는 Pub/Sub를 구독하여 클라이언트에게 전달

사용 예시:
    # Worker (동기)
    from domains._shared.events import get_sync_redis_client, publish_stage_event
    redis_client = get_sync_redis_client()
    publish_stage_event(redis_client, job_id, "vision", "started")

참조: docs/blogs/async/34-sse-HA-architecture.md
"""

from domains._shared.events.redis_client import (
    close_async_cache_client,
    get_async_cache_client,
    get_async_redis_client,
    get_sync_redis_client,
    reset_async_redis_client,
)
from domains._shared.events.redis_streams import (
    DEFAULT_SHARD_COUNT,
    STREAM_MAXLEN,
    STREAM_PREFIX,
    get_shard_for_job,
    get_stream_key,
    publish_stage_event,
    subscribe_events,  # DEPRECATED: 하위 호환성
)

__all__ = [
    "STREAM_PREFIX",
    "STREAM_MAXLEN",
    "DEFAULT_SHARD_COUNT",
    "get_shard_for_job",
    "get_stream_key",
    "publish_stage_event",
    "subscribe_events",  # DEPRECATED: 하위 호환성
    "get_sync_redis_client",
    "get_async_redis_client",
    "get_async_cache_client",
    "reset_async_redis_client",
    "close_async_cache_client",
]
