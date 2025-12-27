"""SSE Broadcast Manager - Redis Pub/Sub 기반.

Event Router + Pub/Sub 아키텍처:
1. Event Router가 Redis Streams 소비 → Pub/Sub 발행
2. SSE-Gateway는 job_id별 채널 구독
3. 어느 Pod에 연결되든 동일 이벤트 수신

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
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncGenerator, ClassVar

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# State KV 접두사
STATE_KEY_PREFIX = "scan:state:"
# Pub/Sub 채널 접두사
PUBSUB_CHANNEL_PREFIX = "sse:events:"


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
    last_seq: int = field(default=-1)  # seq 기반 중복 필터링

    def __hash__(self) -> int:
        """set에 추가할 수 있도록 hash 구현."""
        return id(self)

    def __eq__(self, other: object) -> bool:
        """동일 인스턴스 비교."""
        return self is other

    async def put_event(self, event: dict[str, Any]) -> bool:
        """이벤트 추가 (seq 기반 중복/역순 필터링 + Drop 정책).

        Args:
            event: 이벤트 딕셔너리

        Returns:
            성공 여부
        """
        # seq 기반 중복/역순 필터링
        event_seq = event.get("seq", 0)
        try:
            event_seq = int(event_seq)
        except (ValueError, TypeError):
            event_seq = 0

        if event_seq <= self.last_seq:
            # 이미 전달했거나 역순
            return False

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
        # Redis 클라이언트
        self._redis_client: aioredis.Redis | None = None
        # 종료 플래그
        self._shutdown: bool = False
        # 설정
        self._state_timeout_seconds: int = 30

    @classmethod
    async def get_instance(
        cls,
        redis_url: str = "",
    ) -> SSEBroadcastManager:
        """싱글톤 인스턴스 반환.

        Args:
            redis_url: Redis URL (Pub/Sub + State KV)

        Returns:
            SSEBroadcastManager 인스턴스
        """
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._initialize(redis_url)
                logger.info("broadcast_manager_initialized")
            return cls._instance

    async def _initialize(self, redis_url: str) -> None:
        """Redis 클라이언트 초기화."""
        import redis.asyncio as aioredis

        from config import get_settings

        settings = get_settings()
        redis_url = redis_url or settings.redis_pubsub_url
        self._state_timeout_seconds = settings.state_timeout_seconds

        self._redis_client = aioredis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=60.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True,
            health_check_interval=30,
        )

        logger.info(
            "broadcast_manager_redis_connected",
            extra={"redis_url": redis_url},
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

                if cls._instance._redis_client:
                    await cls._instance._redis_client.close()

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

        # 1. State에서 현재 상태 복구
        state = await self._get_state_snapshot(job_id)
        if state:
            state_seq = state.get("seq", -1)
            try:
                state_seq = int(state_seq)
            except (ValueError, TypeError):
                state_seq = -1
            subscriber.last_seq = state_seq
            yield state  # 현재 상태 먼저 전달

            # 이미 완료된 경우
            if state.get("stage") == "done" or state.get("status") == "failed":
                logger.info(
                    "broadcast_subscribe_already_done",
                    extra={"job_id": job_id},
                )
                return

        # 2. 구독자 등록
        self._subscribers[job_id].add(subscriber)

        # 3. Pub/Sub 구독 시작 (첫 구독자인 경우)
        if job_id not in self._pubsub_tasks or self._pubsub_tasks[job_id].done():
            self._pubsub_tasks[job_id] = asyncio.create_task(self._pubsub_listener(job_id))

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
                    # 무소식 타임아웃 → State 재조회
                    if time.time() - last_event_time > self._state_timeout_seconds:
                        state = await self._get_state_snapshot(job_id)
                        if state:
                            state_seq = state.get("seq", 0)
                            try:
                                state_seq = int(state_seq)
                            except (ValueError, TypeError):
                                state_seq = 0

                            if state_seq > subscriber.last_seq:
                                subscriber.last_seq = state_seq
                                last_event_time = time.time()
                                yield state

                                if state.get("stage") == "done":
                                    logger.info(
                                        "broadcast_subscribe_done_from_state",
                                        extra={"job_id": job_id},
                                    )
                                    return

                    # keepalive
                    yield {"type": "keepalive"}

        finally:
            # 구독 해제
            self._subscribers[job_id].discard(subscriber)

            # 마지막 구독자면 Pub/Sub 취소
            if not self._subscribers[job_id]:
                del self._subscribers[job_id]
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
                },
            )

    async def _pubsub_listener(self, job_id: str) -> None:
        """job_id별 Pub/Sub 리스너.

        Redis Pub/Sub 채널을 구독하고 이벤트를 해당 job_id의
        모든 SubscriberQueue에 분배.
        """
        if not self._redis_client:
            return

        channel = f"{PUBSUB_CHANNEL_PREFIX}{job_id}"
        pubsub = self._redis_client.pubsub()

        try:
            await pubsub.subscribe(channel)
            logger.debug(
                "pubsub_subscribed",
                extra={"job_id": job_id, "channel": channel},
            )

            async for message in pubsub.listen():
                if self._shutdown:
                    break

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

                # 해당 job_id의 모든 구독자에게 분배
                subscribers = self._subscribers.get(job_id, set())
                for subscriber in subscribers:
                    await subscriber.put_event(event)

                if subscribers:
                    logger.debug(
                        "pubsub_event_distributed",
                        extra={
                            "job_id": job_id,
                            "stage": event.get("stage"),
                            "queue_count": len(subscribers),
                        },
                    )

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

    async def _get_state_snapshot(self, job_id: str) -> dict[str, Any] | None:
        """State KV에서 현재 상태 스냅샷 조회.

        재접속/늦은 연결 시 마지막 상태를 즉시 반환.
        """
        if not self._redis_client:
            return None

        try:
            key = f"{STATE_KEY_PREFIX}{job_id}"
            data = await self._redis_client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(
                "state_snapshot_error",
                extra={"job_id": job_id, "error": str(e)},
            )

        return None

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
