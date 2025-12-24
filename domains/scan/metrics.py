"""Scan 도메인 Prometheus 메트릭"""

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
METRICS_PATH = "/metrics/status"


def register_metrics(app: FastAPI) -> None:
    """Prometheus /metrics 엔드포인트 등록"""

    @app.get(METRICS_PATH, include_in_schema=False)
    async def metrics_endpoint() -> Response:
        return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


# ─────────────────────────────────────────────────────────────────────────────
# SSE Completion 엔드포인트 메트릭
# ─────────────────────────────────────────────────────────────────────────────

SSE_CONNECTIONS_ACTIVE = Gauge(
    "scan_sse_connections_active",
    "Number of active SSE connections",
    registry=REGISTRY,
)

SSE_CHAIN_DURATION = Histogram(
    "scan_sse_chain_duration_seconds",
    "Total duration of SSE chain (vision → rule → answer → reward)",
    registry=REGISTRY,
    buckets=(5, 10, 15, 20, 25, 30, 45, 60, 90, 120),
)

SSE_STAGE_DURATION = Histogram(
    "scan_sse_stage_duration_seconds",
    "Duration of each SSE stage",
    labelnames=["stage"],  # vision, rule, answer, reward
    registry=REGISTRY,
    buckets=(0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30),
)

SSE_REQUESTS_TOTAL = Counter(
    "scan_sse_requests_total",
    "Total SSE requests",
    labelnames=["status"],  # success, failed, timeout
    registry=REGISTRY,
)

SSE_TTFB = Histogram(
    "scan_sse_ttfb_seconds",
    "Time to first byte (first SSE event)",
    registry=REGISTRY,
    buckets=(0.1, 0.25, 0.5, 1, 2, 3, 5, 10),
)

# ─────────────────────────────────────────────────────────────────────────────
# Celery Task 메트릭
# ─────────────────────────────────────────────────────────────────────────────

CELERY_TASK_DURATION = Histogram(
    "scan_celery_task_duration_seconds",
    "Duration of Celery task execution",
    labelnames=["task_name", "status"],  # success, failed, retry
    registry=REGISTRY,
    buckets=(0.1, 0.5, 1, 2, 5, 10, 15, 20, 30),
)

CELERY_QUEUE_SIZE = Gauge(
    "scan_celery_queue_size",
    "Number of messages in Celery queue",
    labelnames=["queue"],
    registry=REGISTRY,
)

# ─────────────────────────────────────────────────────────────────────────────
# Scan 도메인 커스텀 비즈니스 메트릭
# ─────────────────────────────────────────────────────────────────────────────

PIPELINE_STEP_LATENCY = Histogram(
    "scan_pipeline_step_duration_seconds",
    "Duration of each step in the waste classification pipeline",
    labelnames=["step"],
    registry=REGISTRY,
    buckets=(
        0.1,
        0.5,
        1.0,
        2.0,
        3.0,
        4.0,
        5.0,
        6.0,
        7.0,
        8.0,
        9.0,
        10.0,
        12.5,
        15.0,
        20.0,
    ),
)

REWARD_MATCH_LATENCY = Histogram(
    "scan_reward_match_duration_seconds",
    "Duration of character reward matching API call",
    registry=REGISTRY,
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

REWARD_MATCH_COUNTER = Counter(
    "scan_reward_match_total",
    "Total count of character reward matching attempts",
    labelnames=["status"],  # success, failed, skipped
    registry=REGISTRY,
)

GRPC_CALL_LATENCY = Histogram(
    "scan_grpc_call_duration_seconds",
    "Duration of gRPC calls to external services",
    labelnames=["service", "method"],
    registry=REGISTRY,
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

GRPC_CALL_COUNTER = Counter(
    "scan_grpc_call_total",
    "Total count of gRPC calls",
    labelnames=["service", "method", "status"],
    registry=REGISTRY,
)
