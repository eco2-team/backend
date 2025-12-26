"""Redis Streams 기반 이벤트 발행/구독 모듈.

Celery Events 대신 Redis Streams를 사용하여
SSE:RabbitMQ 연결 폭발 문제를 해결합니다.

B안 샤딩 아키텍처:
- 스트림을 N개로 샤딩: scan:events:0 ~ scan:events:N-1
- shard = hash(job_id) % N
- Worker는 sharded stream에 publish
- SSE Gateway는 자기 shard만 XREAD

참고:
- [Redis Streams 문서](https://redis.io/docs/latest/develop/data-types/streams/)
- [antirez: Streams Design](http://antirez.com/news/114)
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import TYPE_CHECKING, Any, AsyncGenerator

if TYPE_CHECKING:
    import redis
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────────────

STREAM_PREFIX = "scan:events"
STREAM_MAXLEN = 100  # shard당 최근 100개 이벤트만 유지
STREAM_TTL = 3600  # 1시간 후 만료

# 샤딩 설정 (환경 변수로 오버라이드 가능)
DEFAULT_SHARD_COUNT = int(os.environ.get("SSE_SHARD_COUNT", "4"))


def get_shard_for_job(job_id: str, shard_count: int | None = None) -> int:
    """job_id에 대한 shard 계산.

    Args:
        job_id: Celery task ID (UUID)
        shard_count: 전체 shard 수 (None이면 기본값 사용)

    Returns:
        shard ID (0-based)
    """
    if shard_count is None:
        shard_count = DEFAULT_SHARD_COUNT
    return hash(job_id) % shard_count


def get_stream_key(job_id: str, shard_count: int | None = None) -> str:
    """Sharded Stream key 생성 (B안).

    Args:
        job_id: Chain의 root task ID
        shard_count: 전체 shard 수

    Returns:
        Sharded Stream key (예: "scan:events:2")
    """
    shard = get_shard_for_job(job_id, shard_count)
    return f"{STREAM_PREFIX}:{shard}"


# ─────────────────────────────────────────────────────────────────
# Worker용: 동기 이벤트 발행 (Celery Task에서 호출)
# ─────────────────────────────────────────────────────────────────


def publish_stage_event(
    redis_client: "redis.Redis[Any]",
    job_id: str,
    stage: str,
    status: str,
    result: dict | None = None,
    progress: int | None = None,
) -> str:
    """Worker가 호출: stage 이벤트를 Sharded Redis Streams에 발행 (B안).

    각 Celery Task의 시작/완료 시점에 호출하여
    SSE 클라이언트에게 진행 상황을 전달합니다.

    B안 샤딩:
    - shard = hash(job_id) % shard_count
    - scan:events:{shard}에 발행
    - 이벤트에 job_id 포함 (라우팅용)

    Args:
        redis_client: 동기 Redis 클라이언트 (Celery Worker용)
        job_id: Chain의 root task ID
        stage: 단계명 (queued, vision, rule, answer, reward, done)
        status: 상태 (started, completed, failed)
        result: 완료 시 결과 데이터 (선택)
        progress: 진행률 0~100 (선택)

    Returns:
        발행된 메시지 ID (예: "1735123456789-0")

    Example:
        >>> from domains._shared.events import publish_stage_event
        >>> publish_stage_event(redis, job_id, "vision", "started", progress=0)
        >>> # ... vision 처리 ...
        >>> publish_stage_event(redis, job_id, "vision", "completed", progress=25)
    """
    stream_key = get_stream_key(job_id)

    # B안: job_id를 이벤트에 포함 (SSE Gateway에서 라우팅에 사용)
    event: dict[str, str] = {
        "job_id": job_id,  # 라우팅 키
        "stage": stage,
        "status": status,
        "ts": str(time.time()),
    }

    if progress is not None:
        event["progress"] = str(progress)

    if result:
        event["result"] = json.dumps(result, ensure_ascii=False)

    # XADD + MAXLEN (오래된 이벤트 자동 삭제)
    # approximate=True (~ 접두사)로 효율적 trim
    msg_id = redis_client.xadd(
        stream_key,
        event,
        maxlen=STREAM_MAXLEN,
    )

    # Stream에 TTL 설정 (매번 갱신, 마지막 이벤트 기준)
    redis_client.expire(stream_key, STREAM_TTL)

    shard = get_shard_for_job(job_id)
    logger.debug(
        "stage_event_published",
        extra={
            "job_id": job_id,
            "shard": shard,
            "stream_key": stream_key,
            "stage": stage,
            "status": status,
            "msg_id": msg_id,
        },
    )

    return msg_id


# ─────────────────────────────────────────────────────────────────
# API용: 비동기 이벤트 구독 (SSE 엔드포인트에서 호출)
# ─────────────────────────────────────────────────────────────────


async def subscribe_events(
    redis_client: "aioredis.Redis",  # type: ignore[type-arg]
    job_id: str,
    timeout_ms: int = 5000,
    max_wait_seconds: int = 300,
) -> AsyncGenerator[dict[str, Any], None]:
    """SSE 엔드포인트가 호출: Redis Streams 이벤트 구독.

    Redis Streams의 XREAD 블로킹 읽기를 사용하여
    Worker가 발행하는 stage 이벤트를 실시간으로 수신합니다.

    Args:
        redis_client: 비동기 Redis 클라이언트 (redis.asyncio)
        job_id: Chain의 root task ID
        timeout_ms: XREAD 블로킹 타임아웃 (밀리초, 기본 5초)
        max_wait_seconds: 최대 대기 시간 (초, 기본 5분)

    Yields:
        이벤트 딕셔너리:
        - {"type": "keepalive"}: 타임아웃 시 keepalive
        - {"stage": "vision", "status": "started", ...}: stage 이벤트
        - {"stage": "done", "result": {...}}: 완료 이벤트

    Raises:
        TimeoutError: max_wait_seconds 초과 시

    Example:
        >>> async for event in subscribe_events(redis, job_id):
        ...     if event.get("type") == "keepalive":
        ...         yield ": keepalive\\n\\n"
        ...     else:
        ...         yield format_sse(event)
    """
    stream_key = get_stream_key(job_id)
    last_id = "0"  # 처음부터 읽기 (리플레이 지원)
    start_time = time.time()

    logger.info(
        "subscribe_events_started",
        extra={"job_id": job_id, "stream_key": stream_key},
    )

    while True:
        # 최대 대기 시간 체크
        elapsed = time.time() - start_time
        if elapsed > max_wait_seconds:
            logger.warning(
                "subscribe_events_timeout",
                extra={"job_id": job_id, "elapsed_seconds": elapsed},
            )
            yield {"type": "error", "error": "timeout", "message": "Maximum wait time exceeded"}
            return

        # XREAD: 새 이벤트 대기 (blocking)
        try:
            events = await redis_client.xread(
                {stream_key: last_id},
                block=timeout_ms,
                count=10,
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(
                "subscribe_events_xread_error",
                extra={"job_id": job_id, "error": error_msg},
            )

            # 연결 오류 시 재연결 시도 (1회)
            if "closed" in error_msg.lower() or "connection" in error_msg.lower():
                from domains._shared.events.redis_client import reset_async_redis_client

                try:
                    redis_client = await reset_async_redis_client()
                    logger.info(
                        "subscribe_events_reconnected",
                        extra={"job_id": job_id},
                    )
                    continue  # 재시도
                except Exception as reconnect_error:
                    logger.error(
                        "subscribe_events_reconnect_failed",
                        extra={"job_id": job_id, "error": str(reconnect_error)},
                    )

            yield {"type": "error", "error": "redis_error", "message": error_msg}
            return

        if not events:
            # 타임아웃 → keepalive 이벤트
            yield {"type": "keepalive"}
            continue

        for stream_name, messages in events:
            for msg_id, data in messages:
                # msg_id를 bytes에서 str로 변환 (필요시)
                if isinstance(msg_id, bytes):
                    last_id = msg_id.decode()
                else:
                    last_id = msg_id

                # 바이트 → 문자열 디코딩
                event: dict[str, Any] = {}
                for k, v in data.items():
                    key = k.decode() if isinstance(k, bytes) else k
                    value = v.decode() if isinstance(v, bytes) else v
                    event[key] = value

                # result JSON 파싱
                if "result" in event and isinstance(event["result"], str):
                    try:
                        event["result"] = json.loads(event["result"])
                    except json.JSONDecodeError:
                        pass

                # progress 정수 변환
                if "progress" in event:
                    try:
                        event["progress"] = int(event["progress"])
                    except (ValueError, TypeError):
                        pass

                logger.debug(
                    "subscribe_events_received",
                    extra={
                        "job_id": job_id,
                        "msg_id": last_id,
                        "stage": event.get("stage"),
                        "status": event.get("status"),
                    },
                )

                yield event

                # done 이벤트면 종료
                if event.get("stage") == "done":
                    logger.info(
                        "subscribe_events_completed",
                        extra={"job_id": job_id, "total_time": time.time() - start_time},
                    )
                    return
