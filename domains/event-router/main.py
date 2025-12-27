"""Event Router 메인 애플리케이션.

Redis Streams Consumer Group을 사용하여 이벤트를 소비하고
Redis Pub/Sub로 발행.

참조: docs/blogs/async/34-sse-HA-architecture.md
"""

from __future__ import annotations

import asyncio
import logging
import sys

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from config import get_settings
from core.consumer import StreamConsumer
from core.processor import EventProcessor
from core.reclaimer import PendingReclaimer
from core.tracing import configure_tracing, instrument_redis, shutdown_tracing
from metrics import register_metrics

# ─────────────────────────────────────────────────────────────────
# 로깅 설정
# ─────────────────────────────────────────────────────────────────

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# OpenTelemetry 분산 트레이싱 설정
configure_tracing()
instrument_redis()

# ─────────────────────────────────────────────────────────────────
# FastAPI 앱
# ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Event Router",
    version=settings.service_version,
    docs_url="/docs" if settings.environment != "production" else None,
)

# Prometheus 메트릭 등록
register_metrics(app)

# 전역 상태
redis_streams_client: aioredis.Redis | None = None
redis_pubsub_client: aioredis.Redis | None = None
consumer: StreamConsumer | None = None
reclaimer: PendingReclaimer | None = None
consumer_task: asyncio.Task | None = None
reclaimer_task: asyncio.Task | None = None


# ─────────────────────────────────────────────────────────────────
# 라이프사이클
# ─────────────────────────────────────────────────────────────────


@app.on_event("startup")
async def startup() -> None:
    """앱 시작."""
    global redis_streams_client, redis_pubsub_client, consumer, reclaimer, consumer_task, reclaimer_task

    logger.info(
        "event_router_starting",
        extra={
            "consumer_group": settings.consumer_group,
            "consumer_name": settings.consumer_name,
            "shard_count": settings.shard_count,
        },
    )

    # Redis Streams 연결 (XREADGROUP/XACK)
    redis_streams_client = aioredis.from_url(
        settings.redis_streams_url,
        decode_responses=False,
        socket_timeout=60.0,
        socket_connect_timeout=5.0,
        retry_on_timeout=True,
        health_check_interval=30,
    )

    # Redis Pub/Sub 연결 (PUBLISH only - 실시간 전달용)
    redis_pubsub_client = aioredis.from_url(
        settings.redis_pubsub_url,
        decode_responses=False,
        socket_timeout=60.0,
        socket_connect_timeout=5.0,
        retry_on_timeout=True,
        health_check_interval=30,
    )

    # EventProcessor 초기화
    # - Streams Redis: State KV 갱신 (내구성)
    # - Pub/Sub Redis: 실시간 브로드캐스트
    processor = EventProcessor(
        streams_client=redis_streams_client,
        pubsub_client=redis_pubsub_client,
        state_key_prefix=settings.state_key_prefix,
        published_key_prefix=settings.router_published_prefix,
        pubsub_channel_prefix=settings.pubsub_channel_prefix,
        state_ttl=settings.state_ttl,
        published_ttl=settings.published_ttl,
    )

    # Consumer 초기화 (Streams 클라이언트 사용)
    consumer = StreamConsumer(
        redis_client=redis_streams_client,
        processor=processor,
        consumer_group=settings.consumer_group,
        consumer_name=settings.consumer_name,
        stream_prefix=settings.stream_prefix,
        shard_count=settings.shard_count,
        block_ms=settings.xread_block_ms,
        count=settings.xread_count,
    )

    # Reclaimer 초기화 (Streams 클라이언트 사용)
    reclaimer = PendingReclaimer(
        redis_client=redis_streams_client,
        processor=processor,
        consumer_group=settings.consumer_group,
        consumer_name=settings.consumer_name,
        stream_prefix=settings.stream_prefix,
        shard_count=settings.shard_count,
        min_idle_ms=settings.reclaim_min_idle_ms,
        interval_seconds=settings.reclaim_interval_seconds,
    )

    # Consumer Group 설정
    await consumer.setup()

    # Background tasks 시작
    consumer_task = asyncio.create_task(consumer.consume())
    reclaimer_task = asyncio.create_task(reclaimer.run())

    logger.info("event_router_started")


@app.on_event("shutdown")
async def shutdown() -> None:
    """앱 종료."""
    global consumer, reclaimer, consumer_task, reclaimer_task, redis_streams_client, redis_pubsub_client

    logger.info("event_router_stopping")

    # Consumer 종료
    if consumer:
        await consumer.shutdown()
    if consumer_task:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass

    # Reclaimer 종료
    if reclaimer:
        await reclaimer.shutdown()
    if reclaimer_task:
        reclaimer_task.cancel()
        try:
            await reclaimer_task
        except asyncio.CancelledError:
            pass

    # Redis 연결 종료
    if redis_streams_client:
        await redis_streams_client.close()
    if redis_pubsub_client:
        await redis_pubsub_client.close()

    # OpenTelemetry 종료
    shutdown_tracing()

    logger.info("event_router_stopped")


# ─────────────────────────────────────────────────────────────────
# Health/Ready 엔드포인트
# ─────────────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> JSONResponse:
    """Liveness probe."""
    return JSONResponse({"status": "healthy"})


@app.get("/ready")
async def ready() -> JSONResponse:
    """Readiness probe."""
    # Redis Streams 연결 체크
    if redis_streams_client is None:
        return JSONResponse(
            {"status": "not_ready", "reason": "redis_streams_not_connected"}, status_code=503
        )

    try:
        await redis_streams_client.ping()
    except Exception as e:
        return JSONResponse(
            {"status": "not_ready", "reason": f"redis_streams_ping_failed: {e}"},
            status_code=503,
        )

    # Redis Pub/Sub 연결 체크
    if redis_pubsub_client is None:
        return JSONResponse(
            {"status": "not_ready", "reason": "redis_pubsub_not_connected"}, status_code=503
        )

    try:
        await redis_pubsub_client.ping()
    except Exception as e:
        return JSONResponse(
            {"status": "not_ready", "reason": f"redis_pubsub_ping_failed: {e}"},
            status_code=503,
        )

    # Consumer/Reclaimer task 체크
    if consumer_task is None or consumer_task.done():
        return JSONResponse(
            {"status": "not_ready", "reason": "consumer_not_running"}, status_code=503
        )

    if reclaimer_task is None or reclaimer_task.done():
        return JSONResponse(
            {"status": "not_ready", "reason": "reclaimer_not_running"}, status_code=503
        )

    return JSONResponse({"status": "ready"})


@app.get("/info")
async def info() -> JSONResponse:
    """서비스 정보."""
    return JSONResponse(
        {
            "service": settings.service_name,
            "version": settings.service_version,
            "environment": settings.environment,
            "consumer_group": settings.consumer_group,
            "consumer_name": settings.consumer_name,
            "shard_count": settings.shard_count,
        }
    )
