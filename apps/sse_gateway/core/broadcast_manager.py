"""SSE Broadcast Manager - Redis Pub/Sub 기반.

Event Router + Pub/Sub 아키텍처:
1. Event Router가 Redis Streams 소비 → Pub/Sub 발행
2. SSE-Gateway는 job_id별 채널 구독
3. 어느 Pod에 연결되든 동일 이벤트 수신

분산 트레이싱 통합:
- Pub/Sub 메시지에서 trace context 추출 (trace_id, span_id, traceparent)
- linked span 생성하여 Event Router와 연결
- Jaeger/Kiali에서 Worker → Event Router → SSE Gateway 흐름 추적 가능

이점:
- Pod 수와 무관하게 자유로운 수평확장
- Consistent Hash 불필요
- 장애 복구 용이 (State KV 활용)

참조: docs/blogs/async/34-sse-HA-architecture.md
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncGenerator, ClassVar

from sse_gateway.metrics import (
    SSE_ACTIVE_JOBS,
    SSE_CONNECTIONS_ACTIVE,
    SSE_CONNECTIONS_CLOSED,
    SSE_CONNECTIONS_OPENED,
    SSE_CONNECTION_DURATION,
    SSE_EVENTS_DISTRIBUTED,
    SSE_EVENTS_PER_CONNECTION,
    SSE_PUBSUB_CONNECTED,
    SSE_PUBSUB_MESSAGES_RECEIVED,
    SSE_PUBSUB_SUBSCRIBE_LATENCY,
    SSE_QUEUE_DROPPED,
    SSE_STATE_SNAPSHOT_HITS,
    SSE_STATE_SNAPSHOT_MISSES,
    SSE_TTFB,
)

if TYPE_CHECKING:
    import redis.asyncio as aioredis

# OpenTelemetry 활성화 여부
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() == "true"

logger = logging.getLogger(__name__)

# 도메인별 State KV 접두사
DOMAIN_STATE_PREFIXES = {
    "scan": "scan:state:",
    "chat": "chat:state:",
}
DEFAULT_STATE_PREFIX = "scan:state:"

# Pub/Sub 채널 접두사 (모든 도메인 공통)
PUBSUB_CHANNEL_PREFIX = "sse:events:"

# Token v2: Token Stream + Token State (복구 가능한 토큰 스트리밍)
TOKEN_STREAM_PREFIX = "chat:tokens"  # job별 전용 Token Stream
TOKEN_STATE_PREFIX = "chat:token_state"  # 주기적 누적 텍스트 스냅샷


def get_state_prefix(domain: str | None = None) -> str:
    """도메인별 State KV 접두사 반환."""
    if domain and domain in DOMAIN_STATE_PREFIXES:
        return DOMAIN_STATE_PREFIXES[domain]
    return DEFAULT_STATE_PREFIX


@dataclass
class SubscriberQueue:
    """클라이언트별 Bounded Queue.

    중복 필터링 전략 (정석 패턴):
    - 토큰 이벤트: 전용 seq 기반 (last_token_seq)
    - Stage 이벤트: Redis Stream ID 기반 (단조 증가 보장)

    Stream ID 기반 장점:
    - 분산 환경에서도 순서 보장 (Redis가 발급)
    - timestamp 기반의 clock skew 문제 없음
    - 병렬 노드에서도 정상 이벤트 드랍 방지

    Drop 정책:
    - Queue가 가득 차면 가장 오래된 이벤트 제거
    - done/error 이벤트는 항상 보존
    """

    job_id: str
    domain: str = "scan"  # scan, chat
    queue: asyncio.Queue[dict[str, Any]] = field(default_factory=lambda: asyncio.Queue(maxsize=100))
    created_at: float = field(default_factory=time.time)
    last_event_at: float = field(default_factory=time.time)
    # 토큰 전용 seq (stage seq와 완전 분리)
    last_token_seq: int = field(default=-1)
    # Stage 이벤트용 Stream ID (Redis Stream ID = 단조 증가 보장)
    last_stream_id: str = field(default="0-0")
    # catch-up용 seq (레거시 호환)
    last_seq: int = field(default=-1)

    def __hash__(self) -> int:
        """set에 추가할 수 있도록 hash 구현."""
        return id(self)

    def __eq__(self, other: object) -> bool:
        """동일 인스턴스 비교."""
        return self is other

    @staticmethod
    def _compare_stream_id(a: str, b: str) -> int:
        """Redis Stream ID 비교.

        Stream ID 형식: "{timestamp_ms}-{seq}" (예: "1737415902456-0")
        단조 증가 보장: 같은 Stream에서 나중에 발행된 ID가 항상 더 큼.

        Returns:
            -1 if a < b, 0 if a == b, 1 if a > b
        """

        def parse(sid: str) -> tuple[int, int]:
            try:
                parts = sid.split("-")
                ts = int(parts[0]) if parts[0] else 0
                seq = int(parts[1]) if len(parts) > 1 and parts[1] else 0
                return (ts, seq)
            except (ValueError, IndexError):
                return (0, 0)

        a_parsed, b_parsed = parse(a), parse(b)
        if a_parsed < b_parsed:
            return -1
        elif a_parsed > b_parsed:
            return 1
        return 0

    async def put_event(self, event: dict[str, Any]) -> bool:
        """이벤트 추가 (중복 필터링 + Drop 정책).

        중복 필터링 전략:
        - 토큰 이벤트 (stage="token"): 전용 seq 기반 (last_token_seq)
        - Stage 이벤트: stream_id 기반 (Redis Stream ID = 단조 증가 보장)

        이 방식의 장점:
        1. 토큰/stage seq 충돌 방지 (별도 추적)
        2. 분산 환경에서도 순서 보장 (Stream ID = Redis가 발급)
        3. clock skew, timestamp 해상도 문제 없음

        Args:
            event: 이벤트 딕셔너리

        Returns:
            성공 여부
        """
        event_stage = event.get("stage", "unknown")

        # 토큰 이벤트: 전용 seq 기반 필터링
        # (모든 토큰이 stage:status="token:streaming"으로 동일)
        if event_stage == "token":
            event_seq = event.get("seq", 0)
            try:
                event_seq = int(event_seq)
            except (ValueError, TypeError):
                event_seq = 0

            if event_seq <= self.last_token_seq:
                # 이미 전달했거나 역순
                return False
            self.last_token_seq = event_seq

            # catch-up용 last_seq도 업데이트
            if event_seq > self.last_seq:
                self.last_seq = event_seq
        else:
            # Stage 이벤트: stream_id 기반 필터링 (단조 증가 보장)
            stream_id = event.get("stream_id", "")

            if stream_id:
                # Stream ID 비교 (Redis가 발급한 단조 증가 ID)
                if self._compare_stream_id(stream_id, self.last_stream_id) <= 0:
                    # 이미 전달했거나 역순
                    return False
                self.last_stream_id = stream_id

            # catch-up용 last_seq 업데이트
            event_seq = event.get("seq", 0)
            try:
                event_seq = int(event_seq)
            except (ValueError, TypeError):
                event_seq = 0

            if event_seq > self.last_seq:
                self.last_seq = event_seq

        # done/error는 항상 보존 - Queue가 가득 차면 오래된 것 제거
        if self.queue.full():
            try:
                old_event = self.queue.get_nowait()
                if old_event.get("stage") in ("done", "error"):
                    await self.queue.put(old_event)
                    logger.warning(
                        "queue_event_dropped",
                        extra={
                            "job_id": self.job_id,
                            "dropped_stage": event.get("stage"),
                        },
                    )
                    return False
            except asyncio.QueueEmpty:
                pass

        try:
            self.queue.put_nowait(event)
            self.last_event_at = time.time()
            return True
        except asyncio.QueueFull:
            logger.warning(
                "queue_full_drop",
                extra={"job_id": self.job_id, "stage": event.get("stage")},
            )
            return False


class SSEBroadcastManager:
    """Redis Pub/Sub 기반 SSE Broadcast Manager.

    Redis 역할 분리:
    - Streams Redis: State KV 조회 (scan:state:{job_id}) - 복구용
    - Pub/Sub Redis: 실시간 이벤트 구독 (sse:events:{job_id})

    Event Router가 발행하는 Pub/Sub 메시지를 구독하여
    해당 job_id의 클라이언트들에게 전달.

    사용법:
        manager = await SSEBroadcastManager.get_instance()
        async for event in manager.subscribe(job_id):
            yield format_sse(event)
    """

    _instance: ClassVar[SSEBroadcastManager | None] = None
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    def __init__(self) -> None:
        """초기화."""
        # job_id → SubscriberQueue 집합
        self._subscribers: dict[str, set[SubscriberQueue]] = defaultdict(set)
        # job_id → Pub/Sub listener task
        self._pubsub_tasks: dict[str, asyncio.Task[None]] = {}
        # Redis 클라이언트 (역할별 분리)
        self._streams_client: aioredis.Redis | None = None  # State 조회용
        self._pubsub_client: aioredis.Redis | None = None  # Pub/Sub 구독용
        # 종료 플래그
        self._shutdown: bool = False
        # 설정
        self._state_timeout_seconds: int = 30
        # 도메인별 shard 수 (scan_worker, event_router와 일치 필요)
        self._shard_counts: dict[str, int] = {"scan": 4, "chat": 4}

    @classmethod
    async def get_instance(cls) -> SSEBroadcastManager:
        """싱글톤 인스턴스 반환.

        Returns:
            SSEBroadcastManager 인스턴스
        """
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._initialize()
                logger.info("broadcast_manager_initialized")
            return cls._instance

    async def _initialize(self) -> None:
        """Redis 클라이언트 초기화 (역할별 분리)."""
        import redis.asyncio as aioredis

        from sse_gateway.config import get_settings

        settings = get_settings()
        self._state_timeout_seconds = settings.state_timeout_seconds
        # 도메인별 shard 수 설정 (event_router와 일치)
        self._shard_counts = {
            "scan": settings.shard_count,
            "chat": settings.chat_shard_count,
        }

        # Streams Redis - State 조회용 (내구성)
        self._streams_client = aioredis.from_url(
            settings.redis_streams_url,
            decode_responses=True,
            socket_timeout=60.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True,
            health_check_interval=30,
        )

        # Pub/Sub Redis - 실시간 구독용
        self._pubsub_client = aioredis.from_url(
            settings.redis_pubsub_url,
            decode_responses=True,
            socket_timeout=60.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True,
            health_check_interval=30,
        )

        logger.info(
            "broadcast_manager_redis_connected",
            extra={
                "streams_url": settings.redis_streams_url,
                "pubsub_url": settings.redis_pubsub_url,
                "shard_counts": self._shard_counts,
            },
        )

    @classmethod
    async def shutdown(cls) -> None:
        """매니저 종료."""
        async with cls._lock:
            if cls._instance is not None:
                cls._instance._shutdown = True

                # 모든 Pub/Sub tasks 취소
                for job_id, task in cls._instance._pubsub_tasks.items():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                if cls._instance._streams_client:
                    await cls._instance._streams_client.close()
                if cls._instance._pubsub_client:
                    await cls._instance._pubsub_client.close()

                cls._instance = None
                logger.info("broadcast_manager_shutdown")

    async def subscribe(
        self,
        job_id: str,
        domain: str = "scan",
        timeout_seconds: float = 15.0,
        max_wait_seconds: int = 300,
        last_event_id: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """job_id에 대한 구독 시작.

        Args:
            job_id: Chain의 root task ID
            domain: 서비스 도메인 (scan, chat)
            timeout_seconds: Queue.get() 타임아웃 (keepalive 주기)
            max_wait_seconds: 최대 대기 시간 (기본 5분)
            last_event_id: SSE 표준 Last-Event-ID (재연결 시 중복 방지)

        Yields:
            이벤트 딕셔너리
        """
        subscriber = SubscriberQueue(job_id=job_id, domain=domain)
        # Last-Event-ID 기반 중복 방지: 이미 수신한 이벤트 필터링
        if last_event_id and "-" in last_event_id:
            subscriber.last_stream_id = last_event_id
        connection_start = time.time()
        first_event_time: float | None = None
        event_count = 0
        close_reason = "normal"

        # 메트릭: 연결 시작
        SSE_CONNECTIONS_OPENED.inc()
        SSE_CONNECTIONS_ACTIVE.inc()

        # 1. 구독자 등록 (먼저!)
        self._subscribers[job_id].add(subscriber)
        SSE_ACTIVE_JOBS.set(len(self._subscribers))

        # 2. Pub/Sub 구독 시작 + 완료 대기 (핵심: 먼저 구독해야 이벤트 누락 방지)
        subscribed_event: asyncio.Event | None = None
        if job_id not in self._pubsub_tasks or self._pubsub_tasks[job_id].done():
            logger.info(
                "pubsub_task_creating",
                extra={
                    "job_id": job_id,
                    "domain": domain,
                    "has_pubsub_client": self._pubsub_client is not None,
                },
            )
            subscribed_event = asyncio.Event()
            self._pubsub_tasks[job_id] = asyncio.create_task(
                self._pubsub_listener(job_id, subscribed_event)
            )

        # 구독 완료 대기 (최대 1초)
        if subscribed_event:
            subscribe_start = time.time()
            try:
                await asyncio.wait_for(subscribed_event.wait(), timeout=1.0)
                SSE_PUBSUB_SUBSCRIBE_LATENCY.observe(time.time() - subscribe_start)
            except asyncio.TimeoutError:
                SSE_PUBSUB_SUBSCRIBE_LATENCY.observe(1.0)
                logger.warning(
                    "pubsub_subscribe_timeout",
                    extra={"job_id": job_id, "domain": domain},
                )

        # 3. State에서 현재 상태 복구 (구독 후 조회 = 누락 방지)
        # NOTE: State에서 last_seq를 갱신하지 않음!
        state = await self._get_state_snapshot(job_id, domain)
        if state:
            state_seq = state.get("seq", 0)
            try:
                state_seq = int(state_seq)
            except (ValueError, TypeError):
                state_seq = 0

            # Streams에서 모든 이벤트 catch-up (초기 연결 시 항상 실행)
            # NOTE: 진행 중/완료 상관없이 누락된 이벤트 복구
            logger.info(
                "broadcast_subscribe_catch_up",
                extra={
                    "job_id": job_id,
                    "state_stage": state.get("stage"),
                    "state_seq": state_seq,
                    "last_seq": subscriber.last_seq,
                },
            )

            async for event in self._catch_up_from_streams(
                job_id,
                from_seq=subscriber.last_seq,
                to_seq=state_seq,
                domain=domain,
                after_stream_id=last_event_id,
            ):
                event_count += 1
                if first_event_time is None:
                    first_event_time = time.time()
                    SSE_TTFB.observe(first_event_time - connection_start)
                SSE_EVENTS_DISTRIBUTED.labels(
                    stage=event.get("stage", "unknown"), status="success"
                ).inc()
                # seq 업데이트로 중복 방지
                event_seq = int(event.get("seq", 0))
                if event_seq > subscriber.last_seq:
                    subscriber.last_seq = event_seq
                yield event

            # 이미 완료된 경우: 바로 종료
            if state.get("stage") == "done" or state.get("status") == "failed":
                close_reason = "normal"
                return

        logger.info(
            "broadcast_subscribe_started",
            extra={
                "job_id": job_id,
                "total_subscribers": self._total_subscriber_count(),
                "last_seq": subscriber.last_seq,
            },
        )

        start_time = time.time()
        last_event_time = time.time()

        try:
            while True:
                elapsed = time.time() - start_time
                if elapsed > max_wait_seconds:
                    close_reason = "timeout"
                    logger.warning(
                        "broadcast_subscribe_timeout",
                        extra={"job_id": job_id, "elapsed_seconds": elapsed},
                    )
                    yield {
                        "type": "error",
                        "error": "timeout",
                        "message": "Maximum wait time exceeded",
                    }
                    return

                try:
                    event = await asyncio.wait_for(
                        subscriber.queue.get(),
                        timeout=timeout_seconds,
                    )
                    last_event_time = time.time()
                    event_count += 1
                    if first_event_time is None:
                        first_event_time = time.time()
                        SSE_TTFB.observe(first_event_time - connection_start)
                    SSE_EVENTS_DISTRIBUTED.labels(
                        stage=event.get("stage", "unknown"), status="success"
                    ).inc()
                    yield event

                    # done/error면 종료
                    if event.get("stage") == "done" or event.get("status") == "failed":
                        close_reason = "normal"
                        logger.info(
                            "broadcast_subscribe_done",
                            extra={
                                "job_id": job_id,
                                "total_time": time.time() - start_time,
                            },
                        )
                        return

                except asyncio.TimeoutError:
                    # 무소식 타임아웃 → State 재조회
                    if time.time() - last_event_time > self._state_timeout_seconds:
                        state = await self._get_state_snapshot(job_id, subscriber.domain)
                        if state:
                            state_seq = state.get("seq", 0)
                            try:
                                state_seq = int(state_seq)
                            except (ValueError, TypeError):
                                state_seq = 0

                            # NOTE: last_seq 갱신 없이 State만 emit
                            # 중간 이벤트 필터링 방지
                            if state_seq > subscriber.last_seq:
                                last_event_time = time.time()
                                event_count += 1
                                SSE_EVENTS_DISTRIBUTED.labels(
                                    stage=state.get("stage", "unknown"),
                                    status="success",
                                ).inc()
                                yield state

                                if state.get("stage") == "done":
                                    close_reason = "normal"
                                    logger.info(
                                        "broadcast_subscribe_done_from_state_catch_up",
                                        extra={
                                            "job_id": job_id,
                                            "domain": subscriber.domain,
                                            "state_seq": state_seq,
                                            "last_seq": subscriber.last_seq,
                                        },
                                    )
                                    # Streams에서 모든 이벤트 catch-up (done 포함)
                                    async for event in self._catch_up_from_streams(
                                        job_id,
                                        from_seq=subscriber.last_seq,
                                        to_seq=state_seq,
                                        domain=subscriber.domain,
                                    ):
                                        event_count += 1
                                        SSE_EVENTS_DISTRIBUTED.labels(
                                            stage=event.get("stage", "unknown"),
                                            status="success",
                                        ).inc()
                                        yield event
                                    # catch-up에서 done이 이미 yield됨
                                    return

                    # keepalive
                    yield {"type": "keepalive"}

        finally:
            # 메트릭: 연결 종료
            connection_duration = time.time() - connection_start
            SSE_CONNECTIONS_ACTIVE.dec()
            SSE_CONNECTIONS_CLOSED.labels(reason=close_reason).inc()
            SSE_CONNECTION_DURATION.observe(connection_duration)
            SSE_EVENTS_PER_CONNECTION.observe(event_count)

            # 구독 해제
            self._subscribers[job_id].discard(subscriber)
            SSE_ACTIVE_JOBS.set(len(self._subscribers))

            # 마지막 구독자면 Pub/Sub 취소
            if not self._subscribers[job_id]:
                del self._subscribers[job_id]
                SSE_ACTIVE_JOBS.set(len(self._subscribers))
                if job_id in self._pubsub_tasks:
                    self._pubsub_tasks[job_id].cancel()
                    try:
                        await self._pubsub_tasks[job_id]
                    except asyncio.CancelledError:
                        pass
                    del self._pubsub_tasks[job_id]

            logger.info(
                "broadcast_subscribe_ended",
                extra={
                    "job_id": job_id,
                    "remaining_subscribers": self._total_subscriber_count(),
                    "event_count": event_count,
                    "duration_seconds": connection_duration,
                },
            )

    async def _pubsub_listener(
        self, job_id: str, subscribed_event: asyncio.Event | None = None
    ) -> None:
        """job_id별 Pub/Sub 리스너.

        Redis Pub/Sub 채널을 구독하고 이벤트를 해당 job_id의
        모든 SubscriberQueue에 분배.

        분산 트레이싱:
        - event에서 trace context 추출 (trace_id, span_id, traceparent)
        - linked span 생성하여 Event Router span과 연결
        - 전체 파이프라인 시각화 지원

        Args:
            job_id: 구독할 job ID
            subscribed_event: 구독 완료 시그널 (옵션)
        """
        logger.info(
            "pubsub_listener_started",
            extra={"job_id": job_id, "has_pubsub_client": self._pubsub_client is not None},
        )

        if not self._pubsub_client:
            logger.warning(
                "pubsub_listener_no_client",
                extra={"job_id": job_id},
            )
            if subscribed_event:
                subscribed_event.set()
            return

        channel = f"{PUBSUB_CHANNEL_PREFIX}{job_id}"
        pubsub = self._pubsub_client.pubsub()

        try:
            await pubsub.subscribe(channel)
            SSE_PUBSUB_CONNECTED.set(1)

            logger.info(
                "pubsub_subscribed",
                extra={"job_id": job_id, "channel": channel},
            )

            async for message in pubsub.listen():
                if self._shutdown:
                    break

                # subscription confirmation 메시지 처리
                # NOTE: listen() 시작 후에 실제 SUBSCRIBE가 전송되므로
                # 여기서 subscribed_event를 set해야 race condition 방지
                if message["type"] == "subscribe":
                    if subscribed_event:
                        subscribed_event.set()
                        subscribed_event = None  # 한 번만 set
                    continue

                if message["type"] != "message":
                    continue

                try:
                    event = json.loads(message["data"])
                except json.JSONDecodeError:
                    logger.warning(
                        "pubsub_message_parse_error",
                        extra={"job_id": job_id, "data": message["data"]},
                    )
                    continue

                # 메트릭: Pub/Sub 메시지 수신
                stage = event.get("stage", "unknown")
                seq = event.get("seq", 0)
                SSE_PUBSUB_MESSAGES_RECEIVED.labels(stage=stage).inc()

                logger.info(
                    "pubsub_message_received",
                    extra={
                        "job_id": job_id,
                        "stage": stage,
                        "seq": seq,
                        "channel": channel,
                    },
                )

                # Trace context 추출 및 linked span 생성
                await self._process_event_with_tracing(job_id, event, stage, seq)

        except asyncio.CancelledError:
            logger.debug("pubsub_listener_cancelled", extra={"job_id": job_id})
        except Exception as e:
            logger.error(
                "pubsub_listener_error",
                extra={"job_id": job_id, "error": str(e)},
            )
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            logger.debug("pubsub_unsubscribed", extra={"job_id": job_id})

    async def _process_event_with_tracing(
        self,
        job_id: str,
        event: dict[str, Any],
        stage: str,
        seq: int,
    ) -> None:
        """이벤트 처리 (trace context 포함).

        Event Router에서 전달된 trace context를 추출하여
        linked span을 생성하고 이벤트를 구독자에게 분배.

        Args:
            job_id: 작업 ID
            event: 이벤트 딕셔너리
            stage: 이벤트 단계
            seq: 이벤트 시퀀스
        """
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
                        trace_id_int = int(parts[1], 16)
                        span_id_int = int(parts[2], 16)
                        trace_flags = int(parts[3], 16)

                        parent_ctx = SpanContext(
                            trace_id=trace_id_int,
                            span_id=span_id_int,
                            is_remote=True,
                            trace_flags=TraceFlags(trace_flags),
                        )
                        link = Link(parent_ctx)

                # linked span 생성 (Event Router span과 연결)
                tracer = trace.get_tracer(__name__)
                links = [link] if link else []
                span_context_manager = tracer.start_as_current_span(
                    f"sse_gateway.distribute.{stage}",
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
            # 해당 job_id의 모든 구독자에게 분배
            subscribers = self._subscribers.get(job_id, set())
            distributed_count = 0
            for subscriber in subscribers:
                success = await subscriber.put_event(event)
                if success:
                    distributed_count += 1
                else:
                    SSE_QUEUE_DROPPED.labels(stage=stage).inc()

            if span:
                span.set_attribute("sse.subscriber_count", len(subscribers))
                span.set_attribute("sse.distributed_count", distributed_count)

            if subscribers:
                logger.info(
                    "pubsub_event_distributed",
                    extra={
                        "job_id": job_id,
                        "stage": stage,
                        "seq": seq,
                        "queue_count": len(subscribers),
                        "distributed_count": distributed_count,
                        "trace_id": event.get("trace_id") or None,
                    },
                )
        finally:
            # span context 종료
            if span_context_manager:
                span_context_manager.__exit__(None, None, None)

    async def _get_state_snapshot(self, job_id: str, domain: str = "scan") -> dict[str, Any] | None:
        """State KV에서 현재 상태 스냅샷 조회 (Streams Redis).

        재접속/늦은 연결 시 마지막 상태를 즉시 반환.
        State는 내구성 있는 Streams Redis에 저장됨.

        Args:
            job_id: 작업 ID
            domain: 서비스 도메인 (scan, chat)
        """
        if not self._streams_client:
            SSE_STATE_SNAPSHOT_MISSES.inc()
            return None

        try:
            state_prefix = get_state_prefix(domain)
            key = f"{state_prefix}{job_id}"
            data = await self._streams_client.get(key)
            if data:
                SSE_STATE_SNAPSHOT_HITS.inc()
                return json.loads(data)
            else:
                SSE_STATE_SNAPSHOT_MISSES.inc()
        except Exception as e:
            SSE_STATE_SNAPSHOT_MISSES.inc()
            logger.warning(
                "state_snapshot_error",
                extra={"job_id": job_id, "domain": domain, "error": str(e)},
            )

        return None

    async def _drain_queue_with_grace(
        self, subscriber: SubscriberQueue, grace_seconds: float = 2.0
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Grace period 동안 큐에 남은 이벤트 drain.

        State에서 done을 발견해도 Pub/Sub 큐에 중간 이벤트가 쌓여있을 수 있음.
        grace_seconds 동안 큐에서 이벤트를 꺼내 yield.

        Args:
            subscriber: 구독자 큐
            grace_seconds: 최대 대기 시간

        Yields:
            큐에서 꺼낸 이벤트들
        """
        start_time = time.time()
        drained_count = 0

        while time.time() - start_time < grace_seconds:
            try:
                event = await asyncio.wait_for(
                    subscriber.queue.get(),
                    timeout=0.5,  # 0.5초마다 체크
                )
                drained_count += 1
                yield event

                # done/error면 즉시 종료
                if event.get("stage") == "done" or event.get("status") == "failed":
                    break

            except asyncio.TimeoutError:
                # 큐가 비었으면 종료
                if subscriber.queue.empty():
                    break

        if drained_count > 0:
            logger.info(
                "queue_drained_with_grace",
                extra={
                    "job_id": subscriber.job_id,
                    "drained_count": drained_count,
                    "elapsed_seconds": time.time() - start_time,
                },
            )

    async def _catch_up_from_streams(
        self,
        job_id: str,
        from_seq: int,
        to_seq: int,
        domain: str = "scan",
        after_stream_id: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Streams에서 누락된 이벤트를 catch-up.

        Pub/Sub 구독 전 이벤트가 유실된 경우, Streams에서 직접 읽어 전달.

        Args:
            job_id: job ID
            from_seq: 마지막으로 수신한 seq (이 이후부터 읽음)
            to_seq: 목표 seq (이 seq까지 읽음)
            domain: 서비스 도메인 (scan, chat)
            after_stream_id: 이 stream_id 이후 이벤트만 반환 (Last-Event-ID 기반 중복 방지)

        Yields:
            누락된 이벤트들 (seq 순서대로)
        """
        if not self._streams_client:
            return

        # job_id 기반 shard 계산 (worker와 동일한 해시 함수)
        import hashlib

        shard_count = self._shard_counts.get(domain, 4)
        shard = int.from_bytes(hashlib.md5(job_id.encode()).digest()[:8], "big") % shard_count
        stream_key = f"{domain}:events:{shard}"

        try:
            # Streams에서 전체 이벤트 읽기 (최근 100개)
            messages = await self._streams_client.xrevrange(stream_key, count=100)

            # seq 순서대로 정렬을 위해 먼저 필터링
            # NOTE: decode_responses=True이므로 키/값이 이미 문자열
            events_to_yield = []
            for msg_id, data in messages:
                if data.get("job_id", "") != job_id:
                    continue

                seq = int(data.get("seq", "0"))
                if from_seq < seq <= to_seq:
                    # Last-Event-ID 기반 중복 방지: 이미 수신한 이벤트 스킵
                    if (
                        after_stream_id
                        and SubscriberQueue._compare_stream_id(msg_id, after_stream_id) <= 0
                    ):
                        continue
                    event = dict(data)  # 이미 문자열
                    # stream_id 추가 (SSE id 필드용)
                    event["stream_id"] = msg_id
                    # result 필드 JSON 파싱
                    if event.get("result"):
                        try:
                            event["result"] = json.loads(event["result"])
                        except (json.JSONDecodeError, TypeError):
                            pass
                    # seq를 int로 변환
                    event["seq"] = seq
                    events_to_yield.append((seq, event))

            # seq 순서대로 정렬 후 yield
            events_to_yield.sort(key=lambda x: x[0])

            caught_up_count = 0
            for seq, event in events_to_yield:
                caught_up_count += 1
                yield event

            if caught_up_count > 0:
                logger.info(
                    "streams_catch_up_completed",
                    extra={
                        "job_id": job_id,
                        "from_seq": from_seq,
                        "to_seq": to_seq,
                        "caught_up_count": caught_up_count,
                    },
                )

        except Exception as e:
            logger.warning(
                "streams_catch_up_error",
                extra={
                    "job_id": job_id,
                    "error": str(e),
                },
            )

    def _total_subscriber_count(self) -> int:
        """총 구독자 수."""
        return sum(len(subs) for subs in self._subscribers.values())

    @property
    def active_job_count(self) -> int:
        """활성 job_id 수."""
        return len(self._subscribers)

    @property
    def total_subscriber_count(self) -> int:
        """총 구독자 수."""
        return self._total_subscriber_count()

    # =========================================================
    # Token v2: 복구 가능한 토큰 스트리밍
    # =========================================================

    async def get_token_state(self, job_id: str) -> dict[str, Any] | None:
        """Token State 조회 (누적 텍스트 복구용).

        Token v2: Worker가 주기적으로 저장하는 누적 텍스트 스냅샷.
        재연결 시 전체 텍스트를 즉시 복구할 수 있음.

        Args:
            job_id: 작업 ID

        Returns:
            Token State 또는 None
            - last_seq: 마지막 토큰 seq
            - accumulated: 누적 텍스트
            - accumulated_len: 누적 텍스트 길이
            - completed: 완료 여부 (옵션)
            - updated_at: 마지막 업데이트 시간
        """
        if not self._streams_client:
            return None

        try:
            key = f"{TOKEN_STATE_PREFIX}:{job_id}"
            data = await self._streams_client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(
                "token_state_error",
                extra={"job_id": job_id, "error": str(e)},
            )

        return None

    async def catch_up_tokens(
        self,
        job_id: str,
        from_seq: int = 0,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Token Stream에서 누락된 토큰 복구.

        Token v2: Worker가 저장하는 job별 전용 Token Stream.
        재연결 시 마지막 seq 이후의 토큰을 catch-up.

        Args:
            job_id: 작업 ID
            from_seq: 마지막으로 받은 seq (이 이후부터 복구)

        Yields:
            Token 이벤트
            - stage: "token"
            - status: "streaming"
            - seq: 토큰 seq
            - content: 토큰 내용 (delta)
            - node: 발생 노드 (answer, summarize 등)
        """
        if not self._streams_client:
            return

        token_stream_key = f"{TOKEN_STREAM_PREFIX}:{job_id}"

        try:
            # Token Stream에서 모든 토큰 읽기
            messages = await self._streams_client.xrange(
                token_stream_key,
                min="-",
                max="+",
                count=10000,  # 최대 10000개 (평균 응답 500토큰 대비 충분)
            )

            caught_up_count = 0
            for msg_id, data in messages:
                seq = int(data.get("seq", "0"))
                if seq > from_seq:
                    caught_up_count += 1
                    yield {
                        "stage": "token",
                        "status": "streaming",
                        "seq": seq,
                        "content": data.get("delta", ""),
                        "node": data.get("node", ""),
                        "stream_id": msg_id,  # SSE id 필드용
                    }

            if caught_up_count > 0:
                logger.info(
                    "token_catch_up_completed",
                    extra={
                        "job_id": job_id,
                        "from_seq": from_seq,
                        "caught_up_count": caught_up_count,
                    },
                )

        except Exception as e:
            logger.warning(
                "token_catch_up_error",
                extra={"job_id": job_id, "error": str(e)},
            )

    async def catch_up_from_last_event_id(
        self,
        job_id: str,
        last_event_id: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Last-Event-ID 기반 토큰 복구 (네이티브 SSE 표준).

        브라우저 EventSource 자동 재연결 시 Last-Event-ID 헤더로 전달되는
        Redis Stream ID를 사용하여 누락된 토큰을 XRANGE로 효율적으로 복구.

        Args:
            job_id: 작업 ID
            last_event_id: 마지막으로 수신한 SSE id (Redis Stream ID 형식)

        Yields:
            Token 이벤트 (stage=token)
        """
        if not self._streams_client:
            return

        token_stream_key = f"{TOKEN_STREAM_PREFIX}:{job_id}"

        try:
            # XRANGE with exclusive lower bound: (last_event_id ~ +
            # Redis Stream ID가 다른 stream의 것이라도 timestamp 기반이므로
            # 그 이후 시점의 토큰을 정확히 반환
            messages = await self._streams_client.xrange(
                token_stream_key,
                min=f"({last_event_id}",  # exclusive lower bound
                max="+",
                count=10000,
            )

            caught_up_count = 0
            for msg_id, data in messages:
                caught_up_count += 1
                yield {
                    "stage": "token",
                    "status": "streaming",
                    "seq": int(data.get("seq", "0")),
                    "content": data.get("delta", ""),
                    "node": data.get("node", ""),
                    "stream_id": msg_id,
                }

            if caught_up_count > 0:
                logger.info(
                    "token_catch_up_from_last_event_id",
                    extra={
                        "job_id": job_id,
                        "last_event_id": last_event_id,
                        "caught_up_count": caught_up_count,
                    },
                )

        except Exception as e:
            logger.warning(
                "token_catch_up_from_last_event_id_error",
                extra={
                    "job_id": job_id,
                    "last_event_id": last_event_id,
                    "error": str(e),
                },
            )

    async def get_token_recovery_event(
        self,
        job_id: str,
    ) -> dict[str, Any] | None:
        """Token 복구 이벤트 생성.

        Token v2: 새 연결 시 Token State에서 누적 텍스트를 조회하여
        전체 텍스트를 즉시 전달할 수 있는 복구 이벤트 생성.

        Args:
            job_id: 작업 ID

        Returns:
            복구 이벤트 또는 None
            - stage: "token_recovery"
            - status: "snapshot"
            - accumulated: 누적 텍스트
            - last_seq: 마지막 토큰 seq
            - completed: 완료 여부
        """
        token_state = await self.get_token_state(job_id)
        if not token_state:
            return None

        accumulated = token_state.get("accumulated")
        if not accumulated:
            return None

        return {
            "stage": "token_recovery",
            "status": "snapshot",
            "accumulated": accumulated,
            "last_seq": token_state.get("last_seq", 0),
            "completed": token_state.get("completed", False),
        }
