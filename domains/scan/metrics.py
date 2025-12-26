"""Scan 도메인 Prometheus 메트릭"""

from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
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
