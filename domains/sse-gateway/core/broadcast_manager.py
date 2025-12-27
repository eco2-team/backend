"""개선된 SSE Broadcast Manager - Sharded Stream + Memory Fan-out (B안).

B안 샤딩 아키텍처:
1. 스트림을 N개로 샤딩: scan:events:0 ~ scan:events:N-1
2. Pod마다 assigned_shards가 있고, 자기 shard만 XREAD
3. Istio 라우팅도 동일한 hash(job_id)%N으로 Pod 선택

이점:
- Pod가 늘면 shard를 재분배하여 자연스럽게 수평 확장
- Redis 읽기는 pod당 "담당 shard 수"만큼으로 제한
- "job 이벤트가 다른 pod로 가서 클라가 못 받는" 문제가 구조적으로 해결

참조: docs/blogs/async/31-sse-fanout-optimization.md
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncGenerator, ClassVar

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Sharded Stream 접두사
STREAM_PREFIX = "scan:events"
# 상태 스냅샷 KV 접두사
STATE_KEY_PREFIX = "scan:state:"


@dataclass
class SubscriberQueue:
    """클라이언트별 Bounded Queue.

    Drop 정책:
    - Queue가 가득 차면 가장 오래된 이벤트 제거
    - done/error 이벤트는 항상 보존
    """

    job_id: str
    queue: asyncio.Queue[dict[str, Any]] = field(default_factory=lambda: asyncio.Queue(maxsize=100))
    created_at: float = field(default_factory=time.time)
    last_event_at: float = field(default_factory=time.time)

    def __hash__(self) -> int:
        """set에 추가할 수 있도록 hash 구현."""
        return id(self)  # 인스턴스별 고유 ID 사용

    def __eq__(self, other: object) -> bool:
        """동일 인스턴스 비교."""
        return self is other

    async def put_event(self, event: dict[str, Any]) -> bool:
        """이벤트 추가 (Drop 정책 적용).

        Args:
            event: 이벤트 딕셔너리

        Returns:
            성공 여부
        """
        # done/error는 항상 보존 - Queue가 가득 차면 오래된 것 제거
        if self.queue.full():
            try:
                # 가장 오래된 이벤트 제거 (done/error가 아닌 경우만)
                old_event = self.queue.get_nowait()
                if old_event.get("stage") in ("done", "error"):
                    # done/error는 다시 넣고 새 이벤트 드롭
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
    """Sharded Redis Stream Consumer + Memory Fan-out (B안).

    B안 샤딩 아키텍처:
    - 스트림을 N개로 샤딩: scan:events:0 ~ scan:events:N-1
    - 이 Pod는 shard_id에 해당하는 스트림만 XREAD
    - Istio consistent hash 라우팅으로 동일 job_id는 동일 Pod로

    사용법:
        manager = await SSEBroadcastManager.get_instance()
        async for event in manager.subscribe(job_id):
            yield format_sse(event)

    환경 변수:
        - SSE_SHARD_ID: 이 Pod가 담당하는 shard ID (0-based)
        - SSE_SHARD_COUNT: 전체 shard 수 (default: 4)
    """

    _instance: ClassVar[SSEBroadcastManager | None] = None
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    def __init__(self) -> None:
        """초기화."""
        # job_id → SubscriberQueue 집합
        self._subscribers: dict[str, set[SubscriberQueue]] = defaultdict(set)
        # background consumer task
        self._background_task: asyncio.Task[None] | None = None
        # Redis 클라이언트
        self._streams_client: aioredis.Redis | None = None
        self._cache_client: aioredis.Redis | None = None
        # 종료 플래그
        self._shutdown: bool = False
        # Shard 설정
        self._shard_id: int = 0
        self._shard_count: int = 4
        # 마지막으로 읽은 Stream ID (자기 shard용)
        self._last_id: str = "$"  # tail부터 시작 (과거 이벤트 스킵)

    @classmethod
    async def get_instance(
        cls,
        streams_url: str = "",
        cache_url: str = "",
    ) -> SSEBroadcastManager:
        """싱글톤 인스턴스 반환.

        Args:
            streams_url: Redis Streams URL
            cache_url: Redis Cache URL (KV 스냅샷용)

        Returns:
            SSEBroadcastManager 인스턴스
        """
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._initialize(streams_url, cache_url)
                logger.info("broadcast_manager_initialized")
            return cls._instance

    async def _initialize(self, streams_url: str, cache_url: str) -> None:
        """Redis 클라이언트 및 shard 설정 초기화."""
        import redis.asyncio as aioredis

        from config import get_settings

        settings = get_settings()
        streams_url = streams_url or settings.redis_streams_url
        cache_url = cache_url or settings.redis_cache_url

        # Shard 설정
        self._shard_id = settings.sse_shard_id
        self._shard_count = settings.sse_shard_count

        self._streams_client = aioredis.from_url(
            streams_url,
            decode_responses=False,
            socket_timeout=60.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True,
            health_check_interval=30,
        )

        self._cache_client = aioredis.from_url(
            cache_url,
            decode_responses=True,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
        )

        # Background Consumer 시작
        self._background_task = asyncio.create_task(self._consumer_loop())
        logger.info(
            "broadcast_manager_consumer_started",
            extra={
                "shard_id": self._shard_id,
                "shard_count": self._shard_count,
                "stream_key": f"{STREAM_PREFIX}:{self._shard_id}",
            },
        )

    @classmethod
    async def shutdown(cls) -> None:
        """매니저 종료."""
        async with cls._lock:
            if cls._instance is not None:
                cls._instance._shutdown = True
                if cls._instance._background_task is not None:
                    cls._instance._background_task.cancel()
                    try:
                        await cls._instance._background_task
                    except asyncio.CancelledError:
                        pass
                if cls._instance._streams_client:
                    await cls._instance._streams_client.close()
                if cls._instance._cache_client:
                    await cls._instance._cache_client.close()
                cls._instance = None
                logger.info("broadcast_manager_shutdown")

    async def subscribe(
        self,
        job_id: str,
        timeout_seconds: float = 15.0,
        max_wait_seconds: int = 300,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """job_id에 대한 구독 시작.

        Args:
            job_id: Chain의 root task ID
            timeout_seconds: Queue.get() 타임아웃 (keepalive 주기)
            max_wait_seconds: 최대 대기 시간 (기본 5분)

        Yields:
            이벤트 딕셔너리
        """
        subscriber = SubscriberQueue(job_id=job_id)
        self._subscribers[job_id].add(subscriber)

        logger.info(
            "broadcast_subscribe_started",
            extra={
                "job_id": job_id,
                "total_subscribers": self._total_subscriber_count(),
            },
        )

        start_time = time.time()

        try:
            # 1. Redis Streams에서 이미 발행된 이벤트 리플레이 (Race Condition 해결)
            async for event in self._replay_events_for_job(job_id):
                yield event
                if event.get("stage") == "done" or event.get("status") == "failed":
                    logger.info(
                        "broadcast_subscribe_done_from_replay",
                        extra={"job_id": job_id},
                    )
                    return

            # 2. 실시간 이벤트 수신
            while True:
                elapsed = time.time() - start_time
                if elapsed > max_wait_seconds:
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
                    yield event

                    # done/error면 종료
                    if event.get("stage") == "done" or event.get("status") == "failed":
                        logger.info(
                            "broadcast_subscribe_done",
                            extra={
                                "job_id": job_id,
                                "total_time": time.time() - start_time,
                            },
                        )
                        return

                except asyncio.TimeoutError:
                    # keepalive
                    yield {"type": "keepalive"}

        finally:
            # 구독 해제
            self._subscribers[job_id].discard(subscriber)
            if not self._subscribers[job_id]:
                del self._subscribers[job_id]

            logger.info(
                "broadcast_subscribe_ended",
                extra={
                    "job_id": job_id,
                    "remaining_subscribers": self._total_subscriber_count(),
                },
            )

    async def _replay_events_for_job(self, job_id: str) -> AsyncGenerator[dict[str, Any], None]:
        """Redis Streams에서 해당 job_id의 이벤트 리플레이.

        클라이언트가 구독을 시작할 때 이미 발행된 이벤트를 즉시 전달합니다.
        이로써 Race Condition (SSE 연결 전 이벤트 발행) 문제를 해결합니다.
        """
        if not self._streams_client:
            return

        # 이 job_id가 속한 shard의 Stream 키
        from config import get_settings
        from domains._shared.events.redis_streams import get_shard_for_job

        settings = get_settings()
        shard = get_shard_for_job(job_id, settings.sse_shard_count)
        stream_key = f"{STREAM_PREFIX}:{shard}"

        try:
            # 처음부터 모든 이벤트 읽기 (XRANGE)
            messages = await self._streams_client.xrange(stream_key, min="-", max="+")

            for msg_id, data in messages:
                event = self._parse_event(data)
                # 해당 job_id의 이벤트만 필터링
                if event.get("job_id") == job_id:
                    logger.debug(
                        "broadcast_replay_event",
                        extra={
                            "job_id": job_id,
                            "stage": event.get("stage"),
                            "shard": shard,
                        },
                    )
                    yield event

        except Exception as e:
            logger.warning(
                "broadcast_replay_error",
                extra={"job_id": job_id, "error": str(e)},
            )

    async def _get_state_snapshot(self, job_id: str) -> dict[str, Any] | None:
        """KV에서 현재 상태 스냅샷 조회.

        재접속 시 마지막 상태를 즉시 반환할 수 있음.
        """
        if not self._cache_client:
            return None

        try:
            key = f"{STATE_KEY_PREFIX}{job_id}"
            data = await self._cache_client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(
                "state_snapshot_error",
                extra={"job_id": job_id, "error": str(e)},
            )

        return None

    async def _consumer_loop(self) -> None:
        """Sharded Redis Stream Consumer (B안).

        이 Pod가 담당하는 shard의 Stream에서만 이벤트를 읽고,
        job_id 필드로 라우팅하여 해당 Queue들에 분배.

        shard = hash(job_id) % shard_count
        이 Pod는 shard_id에 해당하는 Stream만 XREAD
        """
        from config import get_settings

        settings = get_settings()

        # 이 Pod가 담당하는 Stream 키
        my_stream_key = f"{STREAM_PREFIX}:{self._shard_id}"

        logger.info(
            "broadcast_consumer_loop_starting",
            extra={
                "shard_id": self._shard_id,
                "stream_key": my_stream_key,
            },
        )

        while not self._shutdown:
            try:
                # 활성 구독자가 없어도 계속 읽기 (새 구독자 대비)
                # 하지만 구독자가 없으면 짧게 sleep
                if not self._subscribers:
                    await asyncio.sleep(0.5)
                    continue

                if not self._streams_client:
                    await asyncio.sleep(1)
                    continue

                # 자기 Shard Stream만 XREAD (O(1))
                events = await self._streams_client.xread(
                    {my_stream_key: self._last_id},
                    block=settings.consumer_xread_block_ms,
                    count=settings.consumer_xread_count,
                )

                if not events:
                    continue

                for stream_key, messages in events:
                    for msg_id, data in messages:
                        # last_id 업데이트
                        self._last_id = msg_id.decode() if isinstance(msg_id, bytes) else msg_id

                        # 이벤트 파싱
                        event = self._parse_event(data)
                        job_id = event.get("job_id")

                        if not job_id:
                            continue

                        # 해당 job_id의 모든 Queue에 이벤트 분배
                        subscribers = self._subscribers.get(job_id, set())
                        for subscriber in subscribers:
                            await subscriber.put_event(event)

                        if subscribers:
                            logger.debug(
                                "broadcast_event_distributed",
                                extra={
                                    "job_id": job_id,
                                    "shard_id": self._shard_id,
                                    "stage": event.get("stage"),
                                    "queue_count": len(subscribers),
                                },
                            )

            except asyncio.CancelledError:
                logger.info("broadcast_consumer_cancelled")
                break
            except Exception as e:
                logger.error(
                    "broadcast_consumer_error",
                    extra={"shard_id": self._shard_id, "error": str(e)},
                )
                await asyncio.sleep(1)

    def _parse_event(self, data: dict[bytes | str, bytes | str]) -> dict[str, Any]:
        """Redis 메시지 파싱."""
        event: dict[str, Any] = {}

        for k, v in data.items():
            key = k.decode() if isinstance(k, bytes) else k
            value = v.decode() if isinstance(v, bytes) else v
            event[key] = value

        # result JSON 파싱
        if "result" in event and isinstance(event["result"], str):
            try:
                event["result"] = json.loads(event["result"])
            except json.JSONDecodeError:
                pass

        # progress 정수 변환
        if "progress" in event:
            try:
                event["progress"] = int(event["progress"])
            except (ValueError, TypeError):
                pass

        return event

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
