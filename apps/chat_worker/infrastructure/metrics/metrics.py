"""Chat Worker Metrics - Prometheus 메트릭 정의.

메트릭 종류:
- Counter: 누적 카운트 (요청 수, 에러 수, 토큰 수)
- Histogram: 분포 측정 (응답 시간, 지연시간)
- Gauge: 현재 값 (활성 작업 수, 활성 스트림 수)

라벨:
- intent: 의도 (waste, character, location, general)
- status: 상태 (success, error)
- provider: LLM 제공자 (openai, gemini)
- node: LangGraph 노드 (answer, summarize)

Token Streaming 메트릭 (부하테스트용):
- chat_stream_tokens_total: 발행된 토큰 수
- chat_stream_token_latency_seconds: Redis XADD 지연시간
- chat_stream_duration_seconds: 스트림 E2E 소요시간
"""

from __future__ import annotations

import functools
import logging
import time
from contextlib import contextmanager
from typing import Callable, Generator

from prometheus_client import Counter, Histogram, Gauge, Info

logger = logging.getLogger(__name__)

# ============================================================
# Service Info
# ============================================================

CHAT_WORKER_INFO = Info(
    "chat_worker",
    "Chat Worker service information",
)
CHAT_WORKER_INFO.info(
    {
        "version": "1.0.0",
        "framework": "langgraph",
    }
)

# ============================================================
# Request Metrics
# ============================================================

CHAT_REQUESTS_TOTAL = Counter(
    "chat_requests_total",
    "Total number of chat requests",
    ["intent", "status", "provider"],
)

CHAT_REQUEST_DURATION = Histogram(
    "chat_request_duration_seconds",
    "Chat request duration in seconds",
    ["intent", "provider"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

CHAT_ERRORS_TOTAL = Counter(
    "chat_errors_total",
    "Total number of chat errors",
    ["intent", "error_type"],
)

CHAT_ACTIVE_JOBS = Gauge(
    "chat_active_jobs",
    "Number of currently active chat jobs",
)

# ============================================================
# Intent Metrics
# ============================================================

CHAT_INTENT_DISTRIBUTION = Counter(
    "chat_intent_distribution_total",
    "Distribution of classified intents",
    ["intent"],
)

# ============================================================
# Vision Metrics
# ============================================================

CHAT_VISION_REQUESTS = Counter(
    "chat_vision_requests_total",
    "Total number of vision analysis requests",
    ["status", "provider"],
)

CHAT_VISION_DURATION = Histogram(
    "chat_vision_duration_seconds",
    "Vision analysis duration in seconds",
    ["provider"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0],
)

# ============================================================
# Subagent Metrics
# ============================================================

CHAT_SUBAGENT_CALLS = Counter(
    "chat_subagent_calls_total",
    "Total number of subagent calls",
    ["subagent", "status"],
)

CHAT_SUBAGENT_DURATION = Histogram(
    "chat_subagent_duration_seconds",
    "Subagent call duration in seconds",
    ["subagent"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

# ============================================================
# Token Usage Metrics
# ============================================================

CHAT_TOKEN_USAGE = Counter(
    "chat_token_usage_total",
    "Total tokens used",
    ["provider", "type"],  # type: input, output
)

# ============================================================
# Token Streaming Metrics (Load Test용)
# ============================================================

# 스트리밍 토큰 처리량
CHAT_STREAM_TOKENS_TOTAL = Counter(
    "chat_stream_tokens_total",
    "Total streaming tokens emitted",
    ["node", "status"],  # node: answer, summarize / status: success, error
)

# 토큰 스트림 요청 수
CHAT_STREAM_REQUESTS_TOTAL = Counter(
    "chat_stream_requests_total",
    "Total token stream requests",
    ["status"],  # status: success, error, recovered
)

# 토큰 발행 지연시간 (Redis XADD)
CHAT_STREAM_TOKEN_LATENCY = Histogram(
    "chat_stream_token_latency_seconds",
    "Token emission latency (Redis XADD)",
    ["node"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25],
)

# 토큰 간 간격 (LLM 스트리밍 속도)
CHAT_STREAM_TOKEN_INTERVAL = Histogram(
    "chat_stream_token_interval_seconds",
    "Interval between tokens (LLM streaming speed)",
    ["provider"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0],
)

# 전체 스트림 완료 시간
CHAT_STREAM_DURATION = Histogram(
    "chat_stream_duration_seconds",
    "Total token stream duration",
    ["node", "status"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0],
)

# 스트림당 토큰 수
CHAT_STREAM_TOKEN_COUNT = Histogram(
    "chat_stream_token_count",
    "Number of tokens per stream",
    ["node"],
    buckets=[10, 50, 100, 200, 500, 1000, 2000],
)

# Token 복구 메트릭
CHAT_STREAM_RECOVERY_TOTAL = Counter(
    "chat_stream_recovery_total",
    "Token stream recovery attempts",
    ["type", "status"],  # type: catch_up, snapshot / status: success, error
)

# 활성 스트림 수 (Gauge)
CHAT_STREAM_ACTIVE = Gauge(
    "chat_stream_active",
    "Number of active token streams",
)

# ============================================================
# Helper Functions
# ============================================================


@contextmanager
def track_request(
    intent: str = "unknown",
    provider: str = "openai",
) -> Generator[None, None, None]:
    """요청 추적 컨텍스트 매니저.

    Usage:
        with track_request(intent="waste", provider="openai"):
            result = await pipeline.ainvoke(state)
    """
    CHAT_ACTIVE_JOBS.inc()
    start_time = time.perf_counter()
    status = "success"

    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        duration = time.perf_counter() - start_time
        CHAT_ACTIVE_JOBS.dec()
        CHAT_REQUESTS_TOTAL.labels(
            intent=intent,
            status=status,
            provider=provider,
        ).inc()
        CHAT_REQUEST_DURATION.labels(
            intent=intent,
            provider=provider,
        ).observe(duration)


def track_intent(intent: str) -> None:
    """의도 분류 추적."""
    CHAT_INTENT_DISTRIBUTION.labels(intent=intent).inc()


def track_vision(
    status: str = "success",
    provider: str = "openai",
    duration: float | None = None,
) -> None:
    """Vision 분석 추적."""
    CHAT_VISION_REQUESTS.labels(status=status, provider=provider).inc()
    if duration is not None:
        CHAT_VISION_DURATION.labels(provider=provider).observe(duration)


def track_subagent(
    subagent: str,
    status: str = "success",
    duration: float | None = None,
) -> None:
    """Subagent 호출 추적."""
    CHAT_SUBAGENT_CALLS.labels(subagent=subagent, status=status).inc()
    if duration is not None:
        CHAT_SUBAGENT_DURATION.labels(subagent=subagent).observe(duration)


def track_tokens(
    provider: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """토큰 사용량 추적."""
    if input_tokens > 0:
        CHAT_TOKEN_USAGE.labels(provider=provider, type="input").inc(input_tokens)
    if output_tokens > 0:
        CHAT_TOKEN_USAGE.labels(provider=provider, type="output").inc(output_tokens)


def track_error(intent: str, error_type: str) -> None:
    """에러 추적."""
    CHAT_ERRORS_TOTAL.labels(intent=intent, error_type=error_type).inc()


# ============================================================
# Token Streaming Helpers (Load Test용)
# ============================================================


class StreamMetricsTracker:
    """토큰 스트림 메트릭 추적기.

    Usage:
        tracker = StreamMetricsTracker(node="answer", provider="openai")
        tracker.start()

        for token in stream:
            tracker.record_token()

        tracker.finish(status="success")
    """

    def __init__(self, node: str = "answer", provider: str = "openai") -> None:
        self.node = node
        self.provider = provider
        self._start_time: float | None = None
        self._last_token_time: float | None = None
        self._token_count: int = 0

    def start(self) -> None:
        """스트림 시작."""
        self._start_time = time.perf_counter()
        self._last_token_time = self._start_time
        self._token_count = 0
        CHAT_STREAM_ACTIVE.inc()

    def record_token(self, latency: float | None = None) -> None:
        """토큰 발행 기록.

        Args:
            latency: Redis XADD 지연시간 (선택)
        """
        current_time = time.perf_counter()
        self._token_count += 1

        # 토큰 카운트
        CHAT_STREAM_TOKENS_TOTAL.labels(node=self.node, status="success").inc()

        # 토큰 간 간격 (LLM 스트리밍 속도)
        if self._last_token_time is not None:
            interval = current_time - self._last_token_time
            CHAT_STREAM_TOKEN_INTERVAL.labels(provider=self.provider).observe(interval)

        # Redis 지연시간
        if latency is not None:
            CHAT_STREAM_TOKEN_LATENCY.labels(node=self.node).observe(latency)

        self._last_token_time = current_time

    def finish(self, status: str = "success") -> None:
        """스트림 완료.

        Args:
            status: 완료 상태 (success, error, recovered)
        """
        CHAT_STREAM_ACTIVE.dec()

        if self._start_time is not None:
            duration = time.perf_counter() - self._start_time
            CHAT_STREAM_DURATION.labels(node=self.node, status=status).observe(duration)

        CHAT_STREAM_TOKEN_COUNT.labels(node=self.node).observe(self._token_count)
        CHAT_STREAM_REQUESTS_TOTAL.labels(status=status).inc()

        logger.debug(
            "Stream completed",
            extra={
                "node": self.node,
                "status": status,
                "token_count": self._token_count,
                "duration": time.perf_counter() - self._start_time if self._start_time else 0,
            },
        )


def track_stream_token(
    node: str = "answer",
    status: str = "success",
    latency: float | None = None,
) -> None:
    """단일 토큰 발행 추적 (간단 버전).

    Args:
        node: 노드명 (answer, summarize)
        status: 상태 (success, error)
        latency: Redis XADD 지연시간
    """
    CHAT_STREAM_TOKENS_TOTAL.labels(node=node, status=status).inc()
    if latency is not None:
        CHAT_STREAM_TOKEN_LATENCY.labels(node=node).observe(latency)


def track_stream_recovery(
    recovery_type: str,
    status: str = "success",
) -> None:
    """토큰 복구 추적.

    Args:
        recovery_type: 복구 타입 (catch_up, snapshot)
        status: 상태 (success, error)
    """
    CHAT_STREAM_RECOVERY_TOTAL.labels(type=recovery_type, status=status).inc()


# ============================================================
# Decorator
# ============================================================


def metrics_tracked(
    intent: str = "unknown",
    provider: str = "openai",
) -> Callable:
    """메트릭 추적 데코레이터.

    Usage:
        @metrics_tracked(intent="waste", provider="openai")
        async def process_waste_query(...):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            with track_request(intent=intent, provider=provider):
                return await func(*args, **kwargs)

        return wrapper

    return decorator
