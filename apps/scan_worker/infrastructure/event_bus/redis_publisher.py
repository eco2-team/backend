"""Redis Event Publisher - EventPublisherPort 구현체.

Redis Streams 기반 멱등성 이벤트 발행.

Event Router + SSE Gateway 아키텍처:
- scan_worker → Redis Streams (scan:events:{shard})
- Event Router → Streams 소비 → Pub/Sub 발행
- SSE Gateway → Pub/Sub 구독 → 클라이언트 전달

분산 트레이싱 통합:
- XADD 시 trace context 포함 (trace_id, span_id, traceparent)
- Event Router가 trace context를 Pub/Sub에 전파
- Jaeger/Kiali에서 전체 파이프라인 시각화 가능
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import redis

from scan_worker.application.classify.ports.event_publisher import EventPublisherPort

logger = logging.getLogger(__name__)

# OpenTelemetry 활성화 여부
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() == "true"


# ─────────────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────────────

STREAM_PREFIX = "scan:events"
PUBLISHED_KEY_PREFIX = "published:"
STREAM_MAXLEN = 10000
PUBLISHED_TTL = 7200  # 2시간

# Stage 순서 (단조증가 seq)
STAGE_ORDER = {
    "queued": 0,
    "vision": 1,
    "rule": 2,
    "answer": 3,
    "reward": 4,
    "done": 5,
}

# 샤딩 설정
DEFAULT_SHARD_COUNT = int(os.environ.get("SSE_SHARD_COUNT", "4"))


# ─────────────────────────────────────────────────────────────────
# 멱등성 Lua Script
# ─────────────────────────────────────────────────────────────────

# NOTE: trace_id, span_id, traceparent 포함하여 분산 트레이싱 지원
IDEMPOTENT_XADD_SCRIPT = """
local publish_key = KEYS[1]  -- published:{job_id}:{stage}:{seq}
local stream_key = KEYS[2]   -- scan:events:{shard}

-- 이미 발행했는지 체크
if redis.call('EXISTS', publish_key) == 1 then
    local existing_msg_id = redis.call('GET', publish_key)
    return {0, existing_msg_id}  -- 이미 발행됨
end

-- XADD 실행 (MAXLEN ~ 로 효율적 trim)
-- ARGV[10]: trace_id, ARGV[11]: span_id, ARGV[12]: traceparent
local msg_id = redis.call('XADD', stream_key, 'MAXLEN', '~', ARGV[1],
    '*',
    'job_id', ARGV[2],
    'stage', ARGV[3],
    'status', ARGV[4],
    'seq', ARGV[5],
    'ts', ARGV[6],
    'progress', ARGV[7],
    'result', ARGV[8],
    'trace_id', ARGV[10],
    'span_id', ARGV[11],
    'traceparent', ARGV[12]
)

-- 발행 마킹 (TTL: 2시간)
redis.call('SETEX', publish_key, ARGV[9], msg_id)

return {1, msg_id}  -- 새로 발행됨
"""


def _get_shard_for_job(job_id: str, shard_count: int | None = None) -> int:
    """job_id에 대한 shard 계산."""
    import hashlib

    if shard_count is None:
        shard_count = DEFAULT_SHARD_COUNT
    hash_bytes = hashlib.md5(job_id.encode()).digest()[:8]
    hash_int = int.from_bytes(hash_bytes, byteorder="big")
    return hash_int % shard_count


def _get_stream_key(job_id: str, shard_count: int | None = None) -> str:
    """Sharded Stream key 생성."""
    shard = _get_shard_for_job(job_id, shard_count)
    return f"{STREAM_PREFIX}:{shard}"


def _get_current_trace_context() -> tuple[str, str, str]:
    """현재 OpenTelemetry span에서 trace context 추출.

    Returns:
        (trace_id, span_id, traceparent) 튜플. OTEL 비활성화 시 빈 문자열.
    """
    if not OTEL_ENABLED:
        return "", "", ""

    try:
        from opentelemetry import trace
        from opentelemetry.trace import format_trace_id, format_span_id

        current_span = trace.get_current_span()
        span_context = current_span.get_span_context()

        if not span_context.is_valid:
            return "", "", ""

        trace_id = format_trace_id(span_context.trace_id)
        span_id = format_span_id(span_context.span_id)
        trace_flags = f"{span_context.trace_flags:02x}"
        traceparent = f"00-{trace_id}-{span_id}-{trace_flags}"

        return trace_id, span_id, traceparent
    except ImportError:
        return "", "", ""
    except Exception as e:
        logger.debug(f"Failed to extract trace context: {e}")
        return "", "", ""


class RedisEventPublisher(EventPublisherPort):
    """Redis Streams 기반 이벤트 발행 구현체.

    멱등성 보장 (Lua Script 사용).
    Event Router + SSE Gateway 호환.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        shard_count: int | None = None,
    ):
        """초기화.

        Args:
            redis_url: Redis URL (None이면 환경변수 사용)
            shard_count: Shard 수 (None이면 기본값 사용)
        """
        self._redis_url = redis_url or os.environ.get(
            "REDIS_STREAMS_URL",
            "redis://rfr-streams-redis.redis.svc.cluster.local:6379/0",
        )
        self._shard_count = shard_count or DEFAULT_SHARD_COUNT
        self._client: redis.Redis | None = None
        logger.info(
            "RedisEventPublisher initialized (url=%s, shards=%d)",
            self._redis_url,
            self._shard_count,
        )

    def _get_client(self) -> redis.Redis:
        """Lazy Redis 클라이언트 생성."""
        if self._client is None:
            self._client = redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
            )
        return self._client

    def publish_stage_event(
        self,
        task_id: str,
        stage: str,
        status: str,
        progress: int | None = None,
        result: dict[str, Any] | None = None,
    ) -> str:
        """단계 이벤트를 Redis Streams에 발행.

        Args:
            task_id: 작업 ID (UUID)
            stage: 단계명 (queued, vision, rule, answer, reward, done)
            status: 상태 (started, completed, failed)
            progress: 진행률 0~100 (선택)
            result: 완료 시 결과 데이터 (선택)

        Returns:
            발행된 메시지 ID
        """
        client = self._get_client()
        stream_key = _get_stream_key(task_id, self._shard_count)

        # 단조증가 seq 계산
        base_seq = STAGE_ORDER.get(stage, 99) * 10
        seq = base_seq + (1 if status == "completed" else 0)

        # 멱등성 키
        publish_key = f"{PUBLISHED_KEY_PREFIX}{task_id}:{stage}:{seq}"

        # 이벤트 데이터
        ts = str(time.time())
        progress_str = str(progress) if progress is not None else ""
        result_str = json.dumps(result, ensure_ascii=False) if result else ""

        # Trace context 추출
        trace_id, span_id, traceparent = _get_current_trace_context()

        # Lua Script 실행
        script = client.register_script(IDEMPOTENT_XADD_SCRIPT)
        result_tuple = script(
            keys=[publish_key, stream_key],
            args=[
                str(STREAM_MAXLEN),  # ARGV[1]
                task_id,  # ARGV[2]
                stage,  # ARGV[3]
                status,  # ARGV[4]
                str(seq),  # ARGV[5]
                ts,  # ARGV[6]
                progress_str,  # ARGV[7]
                result_str,  # ARGV[8]
                str(PUBLISHED_TTL),  # ARGV[9]
                trace_id,  # ARGV[10]
                span_id,  # ARGV[11]
                traceparent,  # ARGV[12]
            ],
        )

        is_new, msg_id = result_tuple
        if isinstance(msg_id, bytes):
            msg_id = msg_id.decode()

        shard = _get_shard_for_job(task_id, self._shard_count)
        if is_new:
            logger.debug(
                "stage_event_published",
                extra={
                    "task_id": task_id,
                    "shard": shard,
                    "stage": stage,
                    "status": status,
                    "msg_id": msg_id,
                },
            )
        else:
            logger.debug(
                "stage_event_duplicate_skipped",
                extra={
                    "task_id": task_id,
                    "shard": shard,
                    "stage": stage,
                    "existing_msg_id": msg_id,
                },
            )

        return msg_id
