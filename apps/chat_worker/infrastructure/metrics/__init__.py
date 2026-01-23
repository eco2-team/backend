"""Chat Worker Metrics - Prometheus 메트릭 및 어댑터."""

from chat_worker.infrastructure.metrics.metrics import (
    # Request metrics
    CHAT_REQUESTS_TOTAL,
    CHAT_REQUEST_DURATION,
    CHAT_ERRORS_TOTAL,
    CHAT_ACTIVE_JOBS,
    CHAT_INTENT_DISTRIBUTION,
    CHAT_VISION_REQUESTS,
    CHAT_SUBAGENT_CALLS,
    CHAT_TOKEN_USAGE,
    # Checkpoint metrics (Read-Through)
    CHAT_CHECKPOINT_PROMOTES_TOTAL,
    CHAT_CHECKPOINT_COLD_MISSES_TOTAL,
    CHAT_CHECKPOINT_PROMOTE_DURATION,
    # Token streaming metrics (Load Test용)
    CHAT_STREAM_TOKENS_TOTAL,
    CHAT_STREAM_REQUESTS_TOTAL,
    CHAT_STREAM_TOKEN_LATENCY,
    CHAT_STREAM_TOKEN_INTERVAL,
    CHAT_STREAM_DURATION,
    CHAT_STREAM_TOKEN_COUNT,
    CHAT_STREAM_RECOVERY_TOTAL,
    CHAT_STREAM_ACTIVE,
    # Helper functions
    track_request,
    track_intent,
    track_vision,
    track_subagent,
    track_tokens,
    track_error,
    track_stream_token,
    track_stream_recovery,
    # Classes
    StreamMetricsTracker,
)
from chat_worker.infrastructure.metrics.prometheus_adapter import (
    PrometheusMetricsAdapter,
    NoOpMetricsAdapter,
)

__all__ = [
    # Request metrics
    "CHAT_REQUESTS_TOTAL",
    "CHAT_REQUEST_DURATION",
    "CHAT_ERRORS_TOTAL",
    "CHAT_ACTIVE_JOBS",
    "CHAT_INTENT_DISTRIBUTION",
    "CHAT_VISION_REQUESTS",
    "CHAT_SUBAGENT_CALLS",
    "CHAT_TOKEN_USAGE",
    # Checkpoint metrics (Read-Through)
    "CHAT_CHECKPOINT_PROMOTES_TOTAL",
    "CHAT_CHECKPOINT_COLD_MISSES_TOTAL",
    "CHAT_CHECKPOINT_PROMOTE_DURATION",
    # Token streaming metrics (Load Test용)
    "CHAT_STREAM_TOKENS_TOTAL",
    "CHAT_STREAM_REQUESTS_TOTAL",
    "CHAT_STREAM_TOKEN_LATENCY",
    "CHAT_STREAM_TOKEN_INTERVAL",
    "CHAT_STREAM_DURATION",
    "CHAT_STREAM_TOKEN_COUNT",
    "CHAT_STREAM_RECOVERY_TOTAL",
    "CHAT_STREAM_ACTIVE",
    # Helper functions
    "track_request",
    "track_intent",
    "track_vision",
    "track_subagent",
    "track_tokens",
    "track_error",
    "track_stream_token",
    "track_stream_recovery",
    # Classes
    "StreamMetricsTracker",
    # Clean Architecture adapters
    "PrometheusMetricsAdapter",
    "NoOpMetricsAdapter",
]
