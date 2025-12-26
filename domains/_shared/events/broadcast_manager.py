"""SSE Broadcast Manager - 단일 Redis Consumer + Memory Fan-out 패턴.

Twitter의 Fan-out 아키텍처 참조:
- 단일 background task가 Redis Streams XREAD
- job_id별 asyncio.Queue로 이벤트 분배

기존 문제:
- 각 SSE 연결마다 독립적인 XREAD 루프 (N:N 구조)
- 50 CCU = 50개 asyncio 코루틴 = CPU 85%

개선:
- 1개의 XREAD 루프가 N개의 Queue에 이벤트 분배 (1:N 구조)
- 50 CCU = 1개 XREAD + 50개 Queue.get() = CPU 대폭 감소

참고:
- docs/blogs/async/31-sse-fanout-optimization.md
- https://velog.io/@akfls221/실무에서-확인한-FAN-OUT과-대규모-트레픽에서의-FAN-OUT
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any, AsyncGenerator, ClassVar

from domains._shared.events.redis_client import get_async_redis_client
from domains._shared.events.redis_streams import STREAM_PREFIX, get_stream_key

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class SSEBroadcastManager:
    """단일 Redis Consumer + Memory Fan-out 패턴.

    Twitter의 Fan-out 아키텍처를 참고하여:
    - 단일 background task가 Redis XREAD로 모든 활성 Stream 구독
    - job_id별 asyncio.Queue로 이벤트 분배

    사용법:
        manager = await SSEBroadcastManager.get_instance()
        async for event in manager.subscribe(job_id):
            yield format_sse(event)
    """

    _instance: ClassVar[SSEBroadcastManager | None] = None
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    def __init__(self) -> None:
        """초기화. get_instance()를 통해서만 호출."""
        # job_id → Queue 집합 (같은 job_id를 여러 클라이언트가 구독 가능)
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        # job_id → 마지막으로 읽은 메시지 ID
        self._last_ids: dict[str, str] = {}
        # background consumer task
        self._background_task: asyncio.Task[None] | None = None
        # Redis 클라이언트
        self._redis_client: aioredis.Redis | None = None  # type: ignore[type-arg]
        # 종료 플래그
        self._shutdown: bool = False

    @classmethod
    async def get_instance(cls) -> SSEBroadcastManager:
        """싱글톤 인스턴스 반환.

        Returns:
            SSEBroadcastManager 인스턴스
        """
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._start_consumer()
                logger.info("broadcast_manager_initialized")
            return cls._instance

    @classmethod
    async def shutdown(cls) -> None:
        """매니저 종료. FastAPI shutdown 이벤트에서 호출."""
        async with cls._lock:
            if cls._instance is not None:
                cls._instance._shutdown = True
                if cls._instance._background_task is not None:
                    cls._instance._background_task.cancel()
                    try:
                        await cls._instance._background_task
                    except asyncio.CancelledError:
                        pass
                cls._instance = None
                logger.info("broadcast_manager_shutdown")

    async def _start_consumer(self) -> None:
        """background consumer task 시작."""
        self._redis_client = await get_async_redis_client()
        self._background_task = asyncio.create_task(self._consumer_loop())
        logger.info("broadcast_manager_consumer_started")

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
            이벤트 딕셔너리:
            - {"type": "keepalive"}: 타임아웃 시 keepalive
            - {"stage": "vision", "status": "started", ...}: stage 이벤트
            - {"stage": "done", "result": {...}}: 완료 이벤트
        """
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        # 구독 등록
        self._subscribers[job_id].add(queue)
        self._last_ids.setdefault(job_id, "0")  # 처음부터 읽기

        logger.info(
            "broadcast_subscribe_started",
            extra={
                "job_id": job_id,
                "total_subscribers": sum(len(q) for q in self._subscribers.values()),
            },
        )

        import time

        start_time = time.time()

        try:
            while True:
                # 최대 대기 시간 체크
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
                    # Queue에서 이벤트 대기
                    event = await asyncio.wait_for(queue.get(), timeout=timeout_seconds)
                    yield event

                    # done 이벤트면 종료
                    if event.get("stage") == "done":
                        logger.info(
                            "broadcast_subscribe_done",
                            extra={
                                "job_id": job_id,
                                "total_time": time.time() - start_time,
                            },
                        )
                        return

                    # 실패 시 종료
                    if event.get("status") == "failed":
                        return

                except asyncio.TimeoutError:
                    # 타임아웃 → keepalive 이벤트
                    yield {"type": "keepalive"}

        finally:
            # 구독 해제
            self._subscribers[job_id].discard(queue)
            if not self._subscribers[job_id]:
                del self._subscribers[job_id]
                self._last_ids.pop(job_id, None)

            logger.info(
                "broadcast_subscribe_ended",
                extra={
                    "job_id": job_id,
                    "remaining_subscribers": sum(len(q) for q in self._subscribers.values()),
                },
            )

    async def _consumer_loop(self) -> None:
        """단일 background task: Redis XREAD → Queue 분배.

        모든 활성 job_id의 Stream을 한 번에 XREAD하고,
        수신한 이벤트를 해당 job_id의 Queue들에 분배합니다.
        """
        while not self._shutdown:
            try:
                # 활성 구독자가 없으면 대기
                if not self._subscribers:
                    await asyncio.sleep(0.1)
                    continue

                # 모든 활성 job_id의 Stream을 XREAD
                streams = {
                    get_stream_key(jid): self._last_ids.get(jid, "0") for jid in self._subscribers
                }

                if not streams:
                    await asyncio.sleep(0.1)
                    continue

                # Redis XREAD (blocking)
                if self._redis_client is None:
                    self._redis_client = await get_async_redis_client()

                events = await self._redis_client.xread(
                    streams,
                    block=5000,  # 5초 블로킹
                    count=100,  # 한 번에 최대 100개
                )

                if not events:
                    continue

                # 이벤트 분배
                for stream_key, messages in events:
                    job_id = self._extract_job_id(stream_key)

                    for msg_id, data in messages:
                        # last_id 업데이트
                        if isinstance(msg_id, bytes):
                            self._last_ids[job_id] = msg_id.decode()
                        else:
                            self._last_ids[job_id] = msg_id

                        # 이벤트 파싱
                        event = self._parse_event(data)

                        # 해당 job_id의 모든 Queue에 이벤트 전달
                        queues = self._subscribers.get(job_id, set())
                        for queue in queues:
                            try:
                                await queue.put(event)
                            except Exception as e:
                                logger.warning(
                                    "broadcast_queue_put_error",
                                    extra={"job_id": job_id, "error": str(e)},
                                )

                        logger.debug(
                            "broadcast_event_distributed",
                            extra={
                                "job_id": job_id,
                                "stage": event.get("stage"),
                                "queue_count": len(queues),
                            },
                        )

            except asyncio.CancelledError:
                logger.info("broadcast_consumer_cancelled")
                break
            except Exception as e:
                logger.error(
                    "broadcast_consumer_error",
                    extra={"error": str(e)},
                )
                await asyncio.sleep(1)  # 오류 시 1초 대기 후 재시도

    def _extract_job_id(self, stream_key: str | bytes) -> str:
        """Stream key에서 job_id 추출.

        Args:
            stream_key: "scan:events:uuid-xxx" 형식

        Returns:
            job_id (uuid 부분)
        """
        if isinstance(stream_key, bytes):
            stream_key = stream_key.decode()
        # "scan:events:uuid-xxx" → "uuid-xxx"
        return stream_key.replace(f"{STREAM_PREFIX}:", "")

    def _parse_event(self, data: dict[bytes | str, bytes | str]) -> dict[str, Any]:
        """Redis 메시지 데이터를 이벤트 딕셔너리로 변환.

        Args:
            data: Redis XREAD에서 받은 raw 데이터

        Returns:
            파싱된 이벤트 딕셔너리
        """
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

    @property
    def active_job_count(self) -> int:
        """활성 job_id 수."""
        return len(self._subscribers)

    @property
    def total_subscriber_count(self) -> int:
        """총 구독자 수 (모든 Queue)."""
        return sum(len(queues) for queues in self._subscribers.values())
