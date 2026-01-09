"""SSE Gateway Prometheus 메트릭

ext-authz 메트릭 구조 참고 (Go prometheus.ExponentialBucketsRange):
- 지수 스케일 버킷: 낮은 latency에 더 촘촘한 분포
- Netflix/Uber/Google SRE 권장: ~2x factor between buckets
- 명확한 label 구조 (result, reason, status)

CCU 측정을 위한 핵심 메트릭:
1. Open Connections (CCU)
2. Event Rate (이벤트 전송률)
3. Connection Churn (연결 churn)
4. Write Latency
5. Queue Backlog
6. Redis Consumer 상태
"""

import math

from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

REGISTRY = CollectorRegistry(auto_describe=True)
METRICS_PATH = "/metrics"


# ─────────────────────────────────────────────────────────────────────────────
# Bucket 생성 유틸리티 (Go prometheus 호환)
# ─────────────────────────────────────────────────────────────────────────────


def exponential_buckets_range(min_val: float, max_val: float, count: int) -> tuple:
    """Go prometheus.ExponentialBucketsRange 호환 구현.

    min_val과 max_val 사이에 count개의 버킷을 지수적으로 분포시킴.
    - 낮은 latency 구간에 더 촘촘한 버킷 (p50/p90/p95/p99 정밀 측정)
    - 높은 latency 구간은 tail 탐지용

    Args:
        min_val: 최소 버킷 값 (초 단위)
        max_val: 최대 버킷 값 (초 단위)
        count: 버킷 개수

    Returns:
        지수 분포된 버킷 튜플

    Example:
        >>> exponential_buckets_range(0.001, 1.0, 12)
        (0.001, 0.0018, 0.0032, 0.0056, 0.01, 0.018, 0.032, 0.056, 0.1, 0.18, 0.32, 0.56, 1.0)
    """
    if count < 2:
        return (min_val, max_val)
    log_min = math.log(min_val)
    log_max = math.log(max_val)
    factor = (log_max - log_min) / (count - 1)
    return tuple(round(math.exp(log_min + factor * i), 4) for i in range(count))


# ─────────────────────────────────────────────────────────────────────────────
# Bucket 설정 (SSE 특화)
#
# SSE 특성:
# - Write Latency: 매우 빠름 (1ms ~ 100ms)
# - XREAD Latency: 블로킹 가능 (1ms ~ 500ms)
# - Connection Duration: 긴 연결 (1s ~ 300s)
# ─────────────────────────────────────────────────────────────────────────────

# SSE Write Latency: 클라이언트에 이벤트 전송 (1ms ~ 100ms, 12 buckets)
SSE_WRITE_BUCKETS = exponential_buckets_range(0.001, 0.1, 12)

# Redis XREAD Latency: 블로킹 읽기 (1ms ~ 500ms, 12 buckets)
XREAD_BUCKETS = exponential_buckets_range(0.001, 0.5, 12)

# Connection Duration: SSE 연결 지속 시간 (1s ~ 300s, 15 buckets)
CONNECTION_DURATION_BUCKETS = exponential_buckets_range(1.0, 300.0, 15)

# Queue Wait Time: 이벤트가 큐에서 대기한 시간 (1ms ~ 1s, 12 buckets)
QUEUE_WAIT_BUCKETS = exponential_buckets_range(0.001, 1.0, 12)


def register_metrics(app: FastAPI) -> None:
    """Prometheus /metrics 엔드포인트 등록"""

    @app.get(METRICS_PATH, include_in_schema=False)
    async def metrics_endpoint() -> Response:
        return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


# ─────────────────────────────────────────────────────────────────────────────
# 1. CCU (동시 연결) 메트릭
# ─────────────────────────────────────────────────────────────────────────────

SSE_CONNECTIONS_ACTIVE = Gauge(
    "sse_gateway_connections_active",
    "Active SSE connections (CCU)",
    registry=REGISTRY,
)

SSE_CONNECTIONS_TOTAL = Counter(
    "sse_gateway_connections_total",
    "Total SSE connections created",
    registry=REGISTRY,
)

SSE_ACTIVE_JOBS = Gauge(
    "sse_gateway_active_jobs",
    "Number of active job subscriptions",
    registry=REGISTRY,
)

SSE_SUBSCRIBERS_PER_JOB = Gauge(
    "sse_gateway_subscribers_per_job",
    "Number of subscribers per job",
    labelnames=["job_id"],
    registry=REGISTRY,
)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Event Rate (이벤트 전송률) 메트릭
# ─────────────────────────────────────────────────────────────────────────────

SSE_EVENTS_RECEIVED = Counter(
    "sse_gateway_events_received_total",
    "Total events received from Redis Streams",
    labelnames=["shard", "stage"],
    registry=REGISTRY,
)

SSE_EVENTS_DISTRIBUTED = Counter(
    "sse_gateway_events_distributed_total",
    "Total events distributed to clients",
    labelnames=["stage", "status"],  # status: success, dropped
    registry=REGISTRY,
)

SSE_EVENTS_PER_CONNECTION = Histogram(
    "sse_gateway_events_per_connection",
    "Number of events sent per connection",
    registry=REGISTRY,
    buckets=(1, 2, 5, 10, 15, 20, 30, 50, 100),
)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Connection Churn (연결 변동) 메트릭
# ─────────────────────────────────────────────────────────────────────────────

SSE_CONNECTIONS_OPENED = Counter(
    "sse_gateway_connections_opened_total",
    "Total connections opened",
    registry=REGISTRY,
)

SSE_CONNECTIONS_CLOSED = Counter(
    "sse_gateway_connections_closed_total",
    "Total connections closed",
    labelnames=["reason"],  # normal, timeout, error, client_disconnect
    registry=REGISTRY,
)

SSE_CONNECTION_DURATION = Histogram(
    "sse_gateway_connection_duration_seconds",
    "Duration of SSE connections",
    registry=REGISTRY,
    buckets=CONNECTION_DURATION_BUCKETS,
)

SSE_RECONNECTIONS = Counter(
    "sse_gateway_reconnections_total",
    "Total reconnection attempts (same job_id within 5s)",
    registry=REGISTRY,
)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Write Latency 메트릭
# ─────────────────────────────────────────────────────────────────────────────

SSE_WRITE_LATENCY = Histogram(
    "sse_gateway_write_latency_seconds",
    "Time to write event to client",
    registry=REGISTRY,
    buckets=SSE_WRITE_BUCKETS,
)

SSE_WRITE_ERRORS = Counter(
    "sse_gateway_write_errors_total",
    "Total write errors",
    labelnames=["error_type"],  # connection_closed, timeout, other
    registry=REGISTRY,
)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Queue Backlog 메트릭
# ─────────────────────────────────────────────────────────────────────────────

SSE_QUEUE_SIZE_TOTAL = Gauge(
    "sse_gateway_queue_size_total",
    "Total queued events across all connections",
    registry=REGISTRY,
)

SSE_QUEUE_DROPPED = Counter(
    "sse_gateway_queue_dropped_total",
    "Total events dropped due to full queue",
    labelnames=["stage"],
    registry=REGISTRY,
)

SSE_QUEUE_WAIT_TIME = Histogram(
    "sse_gateway_queue_wait_seconds",
    "Time events waited in queue before being sent",
    registry=REGISTRY,
    buckets=QUEUE_WAIT_BUCKETS,
)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Redis Consumer 메트릭
# ─────────────────────────────────────────────────────────────────────────────

SSE_REDIS_CONNECTED = Gauge(
    "sse_gateway_redis_connected",
    "Redis connection status (1=connected, 0=disconnected)",
    registry=REGISTRY,
)

SSE_REDIS_XREAD_TOTAL = Counter(
    "sse_gateway_redis_xread_total",
    "Total XREAD operations",
    labelnames=["shard", "result"],  # result: success, timeout, error
    registry=REGISTRY,
)

SSE_REDIS_XREAD_LATENCY = Histogram(
    "sse_gateway_redis_xread_latency_seconds",
    "XREAD latency",
    labelnames=["shard"],
    registry=REGISTRY,
    buckets=XREAD_BUCKETS,
)

SSE_REDIS_XREAD_BATCH_SIZE = Histogram(
    "sse_gateway_redis_xread_batch_size",
    "Number of events returned per XREAD call",
    labelnames=["shard"],
    registry=REGISTRY,
    buckets=(0, 1, 2, 5, 10, 20, 50, 100),
)

SSE_REDIS_CONSUMER_LAG = Gauge(
    "sse_gateway_redis_consumer_lag",
    "Estimated consumer lag (pending events)",
    labelnames=["shard"],
    registry=REGISTRY,
)


# ─────────────────────────────────────────────────────────────────────────────
# 7. State Snapshot 메트릭
# ─────────────────────────────────────────────────────────────────────────────

SSE_STATE_SNAPSHOT_HITS = Counter(
    "sse_gateway_state_snapshot_hits_total",
    "Total state snapshot cache hits (late connect optimization)",
    registry=REGISTRY,
)

SSE_STATE_SNAPSHOT_MISSES = Counter(
    "sse_gateway_state_snapshot_misses_total",
    "Total state snapshot cache misses",
    registry=REGISTRY,
)

SSE_EVENT_REPLAY_TOTAL = Counter(
    "sse_gateway_event_replay_total",
    "Total events replayed from history",
    registry=REGISTRY,
)


# ─────────────────────────────────────────────────────────────────────────────
# 8. 요청/응답 메트릭 (대시보드 호환용)
# ─────────────────────────────────────────────────────────────────────────────

SSE_REQUESTS_TOTAL = Counter(
    "sse_gateway_requests_total",
    "Total SSE requests",
    labelnames=["status"],  # success, timeout, failed
    registry=REGISTRY,
)

SSE_TTFB = Histogram(
    "sse_gateway_ttfb_seconds",
    "Time to first byte (connection open to first event)",
    registry=REGISTRY,
    buckets=exponential_buckets_range(0.001, 10.0, 15),
)

SSE_STREAM_DURATION = Histogram(
    "sse_gateway_stream_duration_seconds",
    "Total stream duration (connection open to close)",
    registry=REGISTRY,
    buckets=exponential_buckets_range(1.0, 300.0, 15),
)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Pub/Sub 구독 메트릭
# ─────────────────────────────────────────────────────────────────────────────

SSE_PUBSUB_CONNECTED = Gauge(
    "sse_gateway_pubsub_connected",
    "Redis Pub/Sub connection status (1=connected, 0=disconnected)",
    registry=REGISTRY,
)

SSE_PUBSUB_MESSAGES_RECEIVED = Counter(
    "sse_gateway_pubsub_messages_received_total",
    "Total messages received from Pub/Sub",
    labelnames=["stage"],
    registry=REGISTRY,
)

SSE_PUBSUB_SUBSCRIBE_LATENCY = Histogram(
    "sse_gateway_pubsub_subscribe_latency_seconds",
    "Time to subscribe to a job channel",
    registry=REGISTRY,
    buckets=exponential_buckets_range(0.001, 1.0, 10),
)
