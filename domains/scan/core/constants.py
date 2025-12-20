"""
Service Constants (Single Source of Truth)

정적 상수 정의 - 빌드 타임에 결정되며 환경변수로 변경되지 않음
"""

from __future__ import annotations

from typing import Sequence

# ─────────────────────────────────────────────────────────────────────────────
# Service Identity
# ─────────────────────────────────────────────────────────────────────────────
SERVICE_NAME = "scan-api"
SERVICE_VERSION = "1.0.8"

# ─────────────────────────────────────────────────────────────────────────────
# Logging Constants (12-Factor App Compliance)
# ─────────────────────────────────────────────────────────────────────────────
ENV_KEY_ENVIRONMENT = "ENVIRONMENT"
ENV_KEY_LOG_LEVEL = "LOG_LEVEL"
ENV_KEY_LOG_FORMAT = "LOG_FORMAT"

DEFAULT_ENVIRONMENT = "dev"
DEFAULT_LOG_LEVEL = "DEBUG"
DEFAULT_LOG_FORMAT = "json"

ECS_VERSION = "8.11.0"

EXCLUDED_LOG_RECORD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "created",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "exc_info",
        "exc_text",
        "thread",
        "threadName",
        "taskName",
        "message",
    }
)

# Noisy loggers to suppress
NOISY_LOGGERS = (
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
    "httpx",
    "httpcore",
    "asyncio",
)

# ─────────────────────────────────────────────────────────────────────────────
# PII Masking Configuration (OWASP compliant)
# ─────────────────────────────────────────────────────────────────────────────
SENSITIVE_FIELD_PATTERNS = frozenset({"password", "secret", "token", "api_key", "authorization"})
MASK_PLACEHOLDER = "***REDACTED***"
MASK_PRESERVE_PREFIX = 4
MASK_PRESERVE_SUFFIX = 4
MASK_MIN_LENGTH = 10

# ─────────────────────────────────────────────────────────────────────────────
# gRPC Constants
# ─────────────────────────────────────────────────────────────────────────────
# 재시도 가능한 gRPC 상태 코드 이름 (런타임에 grpc.StatusCode로 변환)
GRPC_RETRYABLE_STATUS_CODE_NAMES = frozenset(
    {
        "UNAVAILABLE",
        "DEADLINE_EXCEEDED",
        "RESOURCE_EXHAUSTED",
        "ABORTED",
    }
)

DEFAULT_GRPC_TIMEOUT = 5.0
DEFAULT_GRPC_MAX_RETRIES = 3
DEFAULT_GRPC_RETRY_BASE_DELAY = 0.1
DEFAULT_GRPC_RETRY_MAX_DELAY = 2.0
DEFAULT_GRPC_CIRCUIT_FAIL_MAX = 5
DEFAULT_GRPC_CIRCUIT_TIMEOUT = 30

# ─────────────────────────────────────────────────────────────────────────────
# CORS Constants
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_CORS_ORIGINS = [
    "https://frontend1.dev.growbin.app",
    "https://frontend2.dev.growbin.app",
    "https://frontend.dev.growbin.app",
    "http://localhost:5173",
    "https://localhost:5173",
    "http://127.0.0.1:5173",
    "https://127.0.0.1:5173",
]

# ─────────────────────────────────────────────────────────────────────────────
# Prometheus Histogram Bucket Generators (Go prometheus 호환)
# ─────────────────────────────────────────────────────────────────────────────


def linear_buckets(start: float, width: float, count: int) -> tuple[float, ...]:
    """선형 간격 버킷 생성 (Go prometheus.LinearBuckets 호환).

    Example:
        >>> linear_buckets(1.0, 0.5, 5)
        (1.0, 1.5, 2.0, 2.5, 3.0)
    """
    if count < 1:
        raise ValueError("linear_buckets: count must be positive")
    return tuple(round(start + i * width, 6) for i in range(count))


def exponential_buckets(start: float, factor: float, count: int) -> tuple[float, ...]:
    """지수 간격 버킷 생성 (Go prometheus.ExponentialBuckets 호환).

    Example:
        >>> exponential_buckets(0.1, 2, 5)
        (0.1, 0.2, 0.4, 0.8, 1.6)
    """
    if count < 1:
        raise ValueError("exponential_buckets: count must be positive")
    if start <= 0:
        raise ValueError("exponential_buckets: start must be positive")
    if factor <= 1:
        raise ValueError("exponential_buckets: factor must be greater than 1")
    return tuple(round(start * (factor**i), 6) for i in range(count))


def merge_buckets(*bucket_sets: Sequence[float]) -> tuple[float, ...]:
    """여러 버킷 세트를 병합 (중복 제거, 정렬).

    Example:
        >>> merge_buckets((0.1, 0.5), (0.5, 1.0, 2.0))
        (0.1, 0.5, 1.0, 2.0)
    """
    merged = set()
    for bucket_set in bucket_sets:
        merged.update(bucket_set)
    return tuple(sorted(merged))


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Duration Buckets
# ─────────────────────────────────────────────────────────────────────────────

# AI 파이프라인용 버킷 (100ms ~ 60s)
# Nice Round Numbers 원칙 적용
BUCKETS_PIPELINE: tuple[float, ...] = merge_buckets(
    exponential_buckets(start=0.1, factor=2, count=4),  # 0.1, 0.2, 0.4, 0.8
    linear_buckets(start=1.0, width=1.0, count=10),  # 1, 2, ..., 10
    (12.5, 15.0, 20.0),  # 느린 구간
)

BUCKETS_EXTENDED: tuple[float, ...] = merge_buckets(
    BUCKETS_PIPELINE,
    (25.0, 30.0, 45.0, 60.0),  # 타임아웃 구간
)

# gRPC 호출용 버킷 (10ms ~ 5s)
BUCKETS_GRPC: tuple[float, ...] = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)

# 리워드 매칭용 버킷
BUCKETS_REWARD: tuple[float, ...] = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)

# ─────────────────────────────────────────────────────────────────────────────
# Metrics Constants
# ─────────────────────────────────────────────────────────────────────────────
METRIC_PIPELINE_STEP_DURATION = "scan_pipeline_step_duration_seconds"
METRIC_REWARD_MATCH_DURATION = "scan_reward_match_duration_seconds"
METRIC_REWARD_MATCH_TOTAL = "scan_reward_match_total"
METRIC_GRPC_CALL_DURATION = "scan_grpc_call_duration_seconds"
METRIC_GRPC_CALL_TOTAL = "scan_grpc_call_total"
