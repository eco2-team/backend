"""Scan 도메인 Prometheus 메트릭

ext-authz 메트릭 구조 참고 (Go prometheus.ExponentialBucketsRange):
- 지수 스케일 버킷: 낮은 latency에 더 촘촘한 분포
- Netflix/Uber/Google SRE 권장: ~2x factor between buckets
- 명확한 label 구조 (result, reason, status)
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
METRICS_PATH = "/metrics/status"


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
        >>> exponential_buckets_range(0.01, 5.0, 12)
        (0.01, 0.017, 0.029, 0.050, 0.086, 0.147, 0.252, 0.432, 0.740, 1.27, 2.17, 3.71, 5.0)
    """
    if count < 2:
        return (min_val, max_val)
    log_min = math.log(min_val)
    log_max = math.log(max_val)
    factor = (log_max - log_min) / (count - 1)
    return tuple(round(math.exp(log_min + factor * i), 4) for i in range(count))


# ─────────────────────────────────────────────────────────────────────────────
# Bucket 설정 (ext-authz 스타일, ~2x factor)
#
# Netflix/Google SRE 권장:
# - TTFB: 빠른 응답 측정 (10ms ~ 10s)
# - Stage: OpenAI API 호출 포함 (100ms ~ 60s)
# - Chain: 전체 파이프라인 (1s ~ 180s)
# ─────────────────────────────────────────────────────────────────────────────

# TTFB: 첫 이벤트까지 시간 (10ms ~ 10s, 14 buckets, ~1.8x factor)
TTFB_BUCKETS = exponential_buckets_range(0.01, 10.0, 14)

# Stage Duration: OpenAI API 포함 (100ms ~ 60s, 15 buckets, ~1.6x factor)
STAGE_BUCKETS = exponential_buckets_range(0.1, 60.0, 15)

# Chain Duration: 전체 파이프라인 (1s ~ 180s, 15 buckets, ~1.5x factor)
CHAIN_BUCKETS = exponential_buckets_range(1.0, 180.0, 15)

# Celery Task: 개별 태스크 (10ms ~ 60s, 16 buckets, ~1.7x factor)
CELERY_TASK_BUCKETS = exponential_buckets_range(0.01, 60.0, 16)


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
    buckets=CHAIN_BUCKETS,
)

SSE_STAGE_DURATION = Histogram(
    "scan_sse_stage_duration_seconds",
    "Duration of each SSE stage",
    labelnames=["stage"],  # vision, rule, answer, reward
    registry=REGISTRY,
    buckets=STAGE_BUCKETS,
)

SSE_REQUESTS_TOTAL = Counter(
    "scan_sse_requests_total",
    "Total SSE requests by status",
    labelnames=["status"],  # success, failed, timeout
    registry=REGISTRY,
)

SSE_TTFB = Histogram(
    "scan_sse_ttfb_seconds",
    "Time to first byte (first SSE event)",
    registry=REGISTRY,
    buckets=TTFB_BUCKETS,
)

# ─────────────────────────────────────────────────────────────────────────────
# Celery Task 메트릭
# ─────────────────────────────────────────────────────────────────────────────

CELERY_TASK_DURATION = Histogram(
    "scan_celery_task_duration_seconds",
    "Duration of Celery task execution",
    labelnames=["task_name", "status"],  # success, failed, retry
    registry=REGISTRY,
    buckets=CELERY_TASK_BUCKETS,
)

CELERY_TASK_TOTAL = Counter(
    "scan_celery_task_total",
    "Total Celery task executions",
    labelnames=["task_name", "status"],  # success, failed, retry
    registry=REGISTRY,
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
    buckets=STAGE_BUCKETS,  # 동일 스케일 사용
)

# 캐릭터 매칭: 캐시 조회 위주 (10ms ~ 5s, 12 buckets)
REWARD_MATCH_LATENCY = Histogram(
    "scan_reward_match_duration_seconds",
    "Duration of character reward matching (local cache)",
    registry=REGISTRY,
    buckets=exponential_buckets_range(0.01, 5.0, 12),
)

REWARD_MATCH_COUNTER = Counter(
    "scan_reward_match_total",
    "Total count of character reward matching attempts",
    labelnames=["status"],  # success, failed, skipped
    registry=REGISTRY,
)

# gRPC: 빠른 내부 통신 (1ms ~ 2s, 12 buckets)
GRPC_CALL_LATENCY = Histogram(
    "scan_grpc_call_duration_seconds",
    "Duration of gRPC calls to external services",
    labelnames=["service", "method"],
    registry=REGISTRY,
    buckets=exponential_buckets_range(0.001, 2.0, 12),
)

GRPC_CALL_COUNTER = Counter(
    "scan_grpc_call_total",
    "Total count of gRPC calls",
    labelnames=["service", "method", "status"],
    registry=REGISTRY,
)
