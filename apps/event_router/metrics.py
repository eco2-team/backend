"""Event Router Prometheus 메트릭

Event Bus Layer 모니터링을 위한 핵심 메트릭:
1. Consumer Group 상태 (XREADGROUP/XACK)
2. 이벤트 처리율 (processed/skipped)
3. Pub/Sub 발행 상태
4. Reclaimer 상태 (XAUTOCLAIM)
5. 레이턴시 분포
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
    """Go prometheus.ExponentialBucketsRange 호환 구현."""
    if count < 2:
        return (min_val, max_val)
    log_min = math.log(min_val)
    log_max = math.log(max_val)
    factor = (log_max - log_min) / (count - 1)
    return tuple(round(math.exp(log_min + factor * i), 4) for i in range(count))


# ─────────────────────────────────────────────────────────────────────────────
# Bucket 설정
# ─────────────────────────────────────────────────────────────────────────────

# Event Processing Latency: Lua Script 실행 (0.1ms ~ 50ms)
PROCESS_LATENCY_BUCKETS = exponential_buckets_range(0.0001, 0.05, 12)

# Pub/Sub Publish Latency: PUBLISH 명령 (0.1ms ~ 10ms)
PUBLISH_LATENCY_BUCKETS = exponential_buckets_range(0.0001, 0.01, 10)

# XREADGROUP Latency: 블로킹 읽기 (1ms ~ 5s)
XREADGROUP_LATENCY_BUCKETS = exponential_buckets_range(0.001, 5.0, 12)

# Reclaim Latency: XAUTOCLAIM (1ms ~ 100ms)
RECLAIM_LATENCY_BUCKETS = exponential_buckets_range(0.001, 0.1, 10)


def register_metrics(app: FastAPI) -> None:
    """Prometheus /metrics 엔드포인트 등록"""

    @app.get(METRICS_PATH, include_in_schema=False)
    async def metrics_endpoint() -> Response:
        return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Consumer 상태 메트릭
# ─────────────────────────────────────────────────────────────────────────────

EVENT_ROUTER_CONSUMER_STATUS = Gauge(
    "event_router_consumer_status",
    "Consumer status (1=running, 0=stopped)",
    registry=REGISTRY,
)

EVENT_ROUTER_RECLAIMER_STATUS = Gauge(
    "event_router_reclaimer_status",
    "Reclaimer status (1=running, 0=stopped)",
    registry=REGISTRY,
)

EVENT_ROUTER_REDIS_STREAMS_CONNECTED = Gauge(
    "event_router_redis_streams_connected",
    "Redis Streams connection status (1=connected, 0=disconnected)",
    registry=REGISTRY,
)

EVENT_ROUTER_REDIS_PUBSUB_CONNECTED = Gauge(
    "event_router_redis_pubsub_connected",
    "Redis Pub/Sub connection status (1=connected, 0=disconnected)",
    registry=REGISTRY,
)


# ─────────────────────────────────────────────────────────────────────────────
# 2. XREADGROUP 메트릭
# ─────────────────────────────────────────────────────────────────────────────

EVENT_ROUTER_XREADGROUP_TOTAL = Counter(
    "event_router_xreadgroup_total",
    "Total XREADGROUP operations",
    labelnames=["result"],  # success, empty, error
    registry=REGISTRY,
)

EVENT_ROUTER_XREADGROUP_LATENCY = Histogram(
    "event_router_xreadgroup_latency_seconds",
    "XREADGROUP latency",
    registry=REGISTRY,
    buckets=XREADGROUP_LATENCY_BUCKETS,
)

EVENT_ROUTER_XREADGROUP_BATCH_SIZE = Histogram(
    "event_router_xreadgroup_batch_size",
    "Number of events per XREADGROUP call",
    registry=REGISTRY,
    buckets=(0, 1, 2, 5, 10, 20, 50, 100, 200),
)

EVENT_ROUTER_XACK_TOTAL = Counter(
    "event_router_xack_total",
    "Total XACK operations",
    labelnames=["result"],  # success, error
    registry=REGISTRY,
)


# ─────────────────────────────────────────────────────────────────────────────
# 3. 이벤트 처리 메트릭
# ─────────────────────────────────────────────────────────────────────────────

EVENT_ROUTER_EVENTS_PROCESSED = Counter(
    "event_router_events_processed_total",
    "Total events processed (state updated + published)",
    labelnames=["stage"],
    registry=REGISTRY,
)

EVENT_ROUTER_EVENTS_SKIPPED = Counter(
    "event_router_events_skipped_total",
    "Total events skipped (duplicate or out-of-order)",
    labelnames=["reason"],  # duplicate, out_of_order
    registry=REGISTRY,
)

EVENT_ROUTER_PROCESS_LATENCY = Histogram(
    "event_router_process_latency_seconds",
    "Event processing latency (Lua script execution)",
    labelnames=["stage"],
    registry=REGISTRY,
    buckets=PROCESS_LATENCY_BUCKETS,
)

EVENT_ROUTER_PROCESS_ERRORS = Counter(
    "event_router_process_errors_total",
    "Total event processing errors",
    labelnames=["error_type"],
    registry=REGISTRY,
)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Pub/Sub 발행 메트릭
# ─────────────────────────────────────────────────────────────────────────────

EVENT_ROUTER_PUBSUB_PUBLISHED = Counter(
    "event_router_pubsub_published_total",
    "Total events published to Pub/Sub",
    labelnames=["stage"],
    registry=REGISTRY,
)

EVENT_ROUTER_PUBSUB_PUBLISH_LATENCY = Histogram(
    "event_router_pubsub_publish_latency_seconds",
    "Pub/Sub PUBLISH latency",
    registry=REGISTRY,
    buckets=PUBLISH_LATENCY_BUCKETS,
)

EVENT_ROUTER_PUBSUB_PUBLISH_ERRORS = Counter(
    "event_router_pubsub_publish_errors_total",
    "Total Pub/Sub publish errors",
    registry=REGISTRY,
)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Reclaimer 메트릭
# ─────────────────────────────────────────────────────────────────────────────

EVENT_ROUTER_RECLAIM_RUNS = Counter(
    "event_router_reclaim_runs_total",
    "Total reclaim runs",
    labelnames=["result"],  # success, error
    registry=REGISTRY,
)

EVENT_ROUTER_RECLAIM_MESSAGES = Counter(
    "event_router_reclaim_messages_total",
    "Total messages reclaimed via XAUTOCLAIM",
    labelnames=["shard"],
    registry=REGISTRY,
)

EVENT_ROUTER_RECLAIM_LATENCY = Histogram(
    "event_router_reclaim_latency_seconds",
    "XAUTOCLAIM latency per shard",
    labelnames=["shard"],
    registry=REGISTRY,
    buckets=RECLAIM_LATENCY_BUCKETS,
)


# ─────────────────────────────────────────────────────────────────────────────
# 6. State KV 메트릭
# ─────────────────────────────────────────────────────────────────────────────

EVENT_ROUTER_STATE_UPDATES = Counter(
    "event_router_state_updates_total",
    "Total state KV updates",
    labelnames=["stage"],
    registry=REGISTRY,
)

EVENT_ROUTER_PUBLISHED_MARKERS = Counter(
    "event_router_published_markers_total",
    "Total published markers set (idempotency)",
    registry=REGISTRY,
)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Consumer Group 상태 (Gauge)
# ─────────────────────────────────────────────────────────────────────────────

EVENT_ROUTER_CONSUMER_LAG = Gauge(
    "event_router_consumer_lag",
    "Estimated consumer lag (pending entries)",
    labelnames=["shard"],
    registry=REGISTRY,
)

EVENT_ROUTER_ACTIVE_SHARDS = Gauge(
    "event_router_active_shards",
    "Number of active shards being consumed",
    registry=REGISTRY,
)
