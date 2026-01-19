"""Event Router 이벤트 처리기.

Redis 역할 분리:
- Streams Redis: State KV 갱신 ({domain}:state:{job_id}) - 내구성
- Pub/Sub Redis: 실시간 브로드캐스트 (sse:events:{job_id})

멀티 도메인 지원:
- scan:events → scan:state
- chat:events → chat:state

분산 트레이싱 통합:
- Redis Streams 메시지에서 trace context 추출 (trace_id, span_id, traceparent)
- linked span 생성하여 Worker와 연결
- Pub/Sub 메시지에 trace context 포함하여 SSE Gateway로 전파
- Jaeger/Kiali에서 Worker → Event Router → SSE Gateway 흐름 추적 가능

Lua Script는 Streams Redis에서만 실행 (State + 발행 마킹)
Pub/Sub는 별도 Redis로 PUBLISH

참조: docs/blogs/async/34-sse-HA-architecture.md
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import redis.asyncio as aioredis

from event_router.metrics import (
    EVENT_ROUTER_EVENTS_PROCESSED,
    EVENT_ROUTER_EVENTS_SKIPPED,
    EVENT_ROUTER_PROCESS_ERRORS,
    EVENT_ROUTER_PROCESS_LATENCY,
    EVENT_ROUTER_PUBLISHED_MARKERS,
    EVENT_ROUTER_PUBSUB_PUBLISH_ERRORS,
    EVENT_ROUTER_PUBSUB_PUBLISH_LATENCY,
    EVENT_ROUTER_PUBSUB_PUBLISHED,
    EVENT_ROUTER_STATE_UPDATES,
)

logger = logging.getLogger(__name__)

# OpenTelemetry 활성화 여부
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() == "true"

# ─────────────────────────────────────────────────────────────────
# State 갱신 Lua Script (Streams Redis에서 실행)
# ─────────────────────────────────────────────────────────────────

# State 조건부 갱신 + 발행 마킹 (원자적)
# Pub/Sub는 별도 Redis로 분리했으므로 여기서는 State만 처리
#
# 수평 확장 지원:
# - 여러 Pod이 같은 job_id의 이벤트를 동시에 처리할 수 있음
# - 순서가 뒤집혀도 모든 이벤트는 Pub/Sub에 발행됨
# - State는 가장 큰 seq로만 갱신 (최신 상태 유지)
UPDATE_STATE_SCRIPT = """
local state_key = KEYS[1]      -- scan:state:{job_id}
local publish_key = KEYS[2]    -- router:published:{job_id}:{seq}

local event_data = ARGV[1]     -- JSON 이벤트 데이터
local new_seq = tonumber(ARGV[2])
local state_ttl = tonumber(ARGV[3])
local published_ttl = tonumber(ARGV[4])

-- 멱등성: 이미 처리했으면 스킵
if redis.call('EXISTS', publish_key) == 1 then
    return 0  -- 이미 처리됨
end

-- State 조건부 갱신 (더 큰 seq만)
local should_update_state = true
local current = redis.call('GET', state_key)
if current then
    local cur_data = cjson.decode(current)
    local cur_seq = tonumber(cur_data.seq) or 0
    if new_seq <= cur_seq then
        should_update_state = false  -- State 갱신 안함 (더 최신 State 유지)
    end
end

-- State 갱신 (더 큰 seq만 갱신하여 최신 상태 유지)
if should_update_state then
    redis.call('SETEX', state_key, state_ttl, event_data)
end

-- 처리 마킹 (항상)
redis.call('SETEX', publish_key, published_ttl, '1')

-- 항상 1 반환 → Pub/Sub 발행
-- (순서와 상관없이 모든 이벤트가 클라이언트에게 전달됨)
return 1
"""


class EventProcessor:
    """이벤트 처리기.

    Redis Streams에서 읽은 이벤트를 처리:
    - State KV 갱신 (Streams Redis - 내구성)
    - Pub/Sub 발행 (Pub/Sub Redis - 실시간)
    - 멱등성 보장

    멀티 도메인 지원:
    - 이벤트의 stream_name에서 도메인 추출
    - scan:events:0 → scan:state:{job_id}
    - chat:events:0 → chat:state:{job_id}
    """

    def __init__(
        self,
        streams_client: "aioredis.Redis",
        pubsub_client: "aioredis.Redis",
        published_key_prefix: str = "router:published",
        pubsub_channel_prefix: str = "sse:events",
        state_ttl: int = 3600,
        published_ttl: int = 7200,
    ) -> None:
        """초기화.

        Args:
            streams_client: Streams Redis (State KV + 발행 마킹)
            pubsub_client: Pub/Sub Redis (PUBLISH only)
        """
        self._streams_redis = streams_client
        self._pubsub_redis = pubsub_client
        self._published_key_prefix = published_key_prefix
        self._pubsub_channel_prefix = pubsub_channel_prefix
        self._state_ttl = state_ttl
        self._published_ttl = published_ttl
        self._script: Any = None

    def _get_state_prefix(self, stream_name: str) -> str:
        """스트림 이름에서 state prefix 유도.

        scan:events:0 → scan:state
        chat:events:0 → chat:state
        """
        # stream_name = "{domain}:events:{shard}"
        parts = stream_name.split(":")
        if len(parts) >= 2:
            domain = parts[0]  # scan, chat
            return f"{domain}:state"
        return "scan:state"  # 기본값

    async def _ensure_script(self) -> None:
        """Lua Script 등록 (Streams Redis에)."""
        if self._script is None:
            self._script = self._streams_redis.register_script(UPDATE_STATE_SCRIPT)

    async def process_event(self, event: dict[str, Any], stream_name: str | None = None) -> bool:
        """이벤트 처리 (멱등성 보장).

        1. Streams Redis에서 State 갱신 (Lua Script)
           - Token 이벤트는 State 갱신하지 않음 (스트리밍 데이터)
        2. State 갱신 성공 시 Pub/Sub Redis로 발행 (trace context 포함)

        분산 트레이싱:
        - event에서 trace context 추출 (trace_id, span_id, traceparent)
        - linked span 생성하여 Worker span과 연결
        - Pub/Sub 메시지에 trace context 포함

        Args:
            event: Redis Streams 이벤트
            stream_name: 이벤트가 온 스트림 이름 (도메인별 state prefix 결정용)

        Returns:
            True if processed, False if skipped (duplicate or out-of-order)
        """
        await self._ensure_script()

        job_id = event.get("job_id")
        if not job_id:
            logger.warning("process_event_missing_job_id", extra={"event": event})
            EVENT_ROUTER_EVENTS_SKIPPED.labels(reason="missing_job_id").inc()
            return False

        seq = event.get("seq", 0)
        try:
            seq = int(seq)
        except (ValueError, TypeError):
            seq = 0

        stage = event.get("stage", "unknown")

        # Trace context 추출 및 linked span 생성
        span_context_manager = None

        if OTEL_ENABLED:
            try:
                from opentelemetry import trace
                from opentelemetry.trace import SpanContext, TraceFlags, Link

                # 이벤트에서 traceparent 추출 및 파싱
                traceparent = event.get("traceparent", "")
                link = None

                if traceparent:
                    # W3C TraceContext: 00-{trace_id}-{span_id}-{trace_flags}
                    parts = traceparent.split("-")
                    if len(parts) == 4:
                        trace_id = int(parts[1], 16)
                        span_id = int(parts[2], 16)
                        trace_flags = int(parts[3], 16)

                        parent_ctx = SpanContext(
                            trace_id=trace_id,
                            span_id=span_id,
                            is_remote=True,
                            trace_flags=TraceFlags(trace_flags),
                        )
                        link = Link(parent_ctx)

                # linked span 생성 (Worker span과 연결)
                tracer = trace.get_tracer(__name__)
                links = [link] if link else []
                span_context_manager = tracer.start_as_current_span(
                    f"event_router.process.{stage}",
                    links=links,
                    attributes={
                        "job.id": job_id,
                        "event.stage": stage,
                        "event.seq": seq,
                    },
                )
            except ImportError:
                pass
            except Exception as e:
                logger.debug(f"Failed to create linked span: {e}")

        # span context 진입
        span = None
        if span_context_manager:
            span = span_context_manager.__enter__()

        try:
            return await self._process_event_inner(event, job_id, seq, stage, stream_name, span)
        finally:
            # span context 종료
            if span_context_manager:
                span_context_manager.__exit__(None, None, None)

    async def _process_event_inner(
        self,
        event: dict[str, Any],
        job_id: str,
        seq: int,
        stage: str,
        stream_name: str | None,
        span: Any,
    ) -> bool:
        """이벤트 처리 내부 로직."""

        # Token 이벤트는 State 갱신 없이 Pub/Sub만 발행
        # Token은 순간적인 스트리밍 데이터이므로 State에 저장할 필요 없음
        is_token_event = stage == "token"

        # 도메인별 state prefix 결정
        state_prefix = self._get_state_prefix(stream_name or "scan:events:0")

        # Redis 키
        state_key = f"{state_prefix}:{job_id}"
        publish_key = f"{self._published_key_prefix}:{job_id}:{seq}"
        channel = f"{self._pubsub_channel_prefix}:{job_id}"

        # 이벤트 JSON
        event_data = json.dumps(event, ensure_ascii=False)

        # Token 이벤트: State 갱신 없이 Pub/Sub만 발행
        # Token은 순간적인 스트리밍 데이터이므로 State에 저장하면 안됨
        # (done 이벤트보다 높은 seq로 인해 최종 상태가 덮어씌워지는 문제 방지)
        #
        # Token v2: Worker에서 Token Stream + State를 저장하므로
        # 여기서는 Pub/Sub 발행만 담당 (재시도 로직 추가)
        if is_token_event:
            start_time = time.perf_counter()

            # 재시도 로직 (최대 3회)
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await self._pubsub_redis.publish(channel, event_data)
                    EVENT_ROUTER_PUBSUB_PUBLISHED.labels(stage=stage).inc()
                    EVENT_ROUTER_PUBSUB_PUBLISH_LATENCY.observe(time.perf_counter() - start_time)
                    logger.info(
                        "token_event_published",
                        extra={
                            "job_id": job_id,
                            "seq": seq,
                            "channel": channel,
                            "attempt": attempt + 1,
                        },
                    )
                    break  # 성공 시 루프 종료
                except Exception as e:
                    if attempt == max_retries - 1:
                        # 마지막 시도도 실패
                        EVENT_ROUTER_PUBSUB_PUBLISH_ERRORS.inc()
                        logger.warning(
                            "token_pubsub_publish_failed",
                            extra={
                                "job_id": job_id,
                                "seq": seq,
                                "channel": channel,
                                "error": str(e),
                                "attempts": max_retries,
                            },
                        )
                        # Token v2: 실패해도 Worker의 Token Stream에 저장되어 있음
                        # SSE Gateway의 catch-up으로 복구 가능
                        return False
                    # 재시도 대기 (exponential backoff)
                    await asyncio.sleep(0.1 * (attempt + 1))

            EVENT_ROUTER_EVENTS_PROCESSED.labels(stage=stage).inc()
            return True

        # Step 1: State 갱신 (Streams Redis - Lua Script)
        start_time = time.perf_counter()
        try:
            result = await self._script(
                keys=[state_key, publish_key],
                args=[event_data, seq, self._state_ttl, self._published_ttl],
            )
        except Exception:
            EVENT_ROUTER_PROCESS_ERRORS.labels(error_type="lua_script").inc()
            raise
        finally:
            process_latency = time.perf_counter() - start_time
            EVENT_ROUTER_PROCESS_LATENCY.labels(stage=stage).observe(process_latency)

        if result == 1:
            # State가 갱신됨
            EVENT_ROUTER_STATE_UPDATES.labels(stage=stage).inc()
            EVENT_ROUTER_PUBLISHED_MARKERS.inc()

            # Step 2: Pub/Sub 발행 (별도 Redis) - 재시도 로직 추가
            publish_start = time.perf_counter()
            max_retries = 3
            publish_success = False

            for attempt in range(max_retries):
                try:
                    await self._pubsub_redis.publish(channel, event_data)
                    EVENT_ROUTER_PUBSUB_PUBLISHED.labels(stage=stage).inc()
                    EVENT_ROUTER_PUBSUB_PUBLISH_LATENCY.observe(time.perf_counter() - publish_start)
                    publish_success = True

                    if span:
                        span.set_attribute("pubsub.channel", channel)
                        span.set_attribute("pubsub.published", True)

                    # INFO 레벨로 변경하여 이벤트 처리 추적 가능
                    logger.info(
                        "event_processed",
                        extra={
                            "job_id": job_id,
                            "stage": stage,
                            "seq": seq,
                            "channel": channel,
                            "attempt": attempt + 1,
                        },
                    )
                    break  # 성공 시 루프 종료

                except Exception as e:
                    if attempt == max_retries - 1:
                        # 마지막 시도도 실패
                        EVENT_ROUTER_PUBSUB_PUBLISH_ERRORS.inc()
                        if span:
                            span.set_attribute("pubsub.published", False)
                            span.set_attribute("pubsub.error", str(e))

                        logger.error(
                            "pubsub_publish_failed",
                            extra={
                                "job_id": job_id,
                                "stage": stage,
                                "seq": seq,
                                "channel": channel,
                                "error": str(e),
                                "attempts": max_retries,
                            },
                        )
                    else:
                        logger.warning(
                            "pubsub_publish_retry",
                            extra={
                                "job_id": job_id,
                                "stage": stage,
                                "seq": seq,
                                "attempt": attempt + 1,
                                "error": str(e),
                            },
                        )
                        # 재시도 대기 (exponential backoff)
                        await asyncio.sleep(0.1 * (attempt + 1))

            EVENT_ROUTER_EVENTS_PROCESSED.labels(stage=stage).inc()
            return publish_success
        else:
            EVENT_ROUTER_EVENTS_SKIPPED.labels(reason="duplicate_or_out_of_order").inc()
            if span:
                span.set_attribute("event.skipped", True)
                span.set_attribute("event.skip_reason", "duplicate_or_out_of_order")

            logger.debug(
                "event_skipped",
                extra={
                    "job_id": job_id,
                    "stage": stage,
                    "seq": seq,
                    "reason": "duplicate_or_out_of_order",
                },
            )
            return False

    async def process_batch(self, events: list[dict[str, Any]]) -> int:
        """배치 이벤트 처리.

        Args:
            events: 이벤트 목록

        Returns:
            처리된 이벤트 수
        """
        processed_count = 0
        for event in events:
            try:
                if await self.process_event(event):
                    processed_count += 1
            except Exception as e:
                logger.error(
                    "process_event_error",
                    extra={
                        "job_id": event.get("job_id"),
                        "error": str(e),
                    },
                )
        return processed_count
