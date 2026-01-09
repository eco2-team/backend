"""Event Router Reclaimer.

XAUTOCLAIM을 사용하여 오래된 Pending 메시지를 재할당.
장애 복구 메커니즘.

참조: docs/blogs/async/34-sse-HA-architecture.md
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import redis.asyncio as aioredis

from event_router.metrics import (
    EVENT_ROUTER_RECLAIM_LATENCY,
    EVENT_ROUTER_RECLAIM_MESSAGES,
    EVENT_ROUTER_RECLAIM_RUNS,
    EVENT_ROUTER_RECLAIMER_STATUS,
)

from .processor import EventProcessor

logger = logging.getLogger(__name__)


class PendingReclaimer:
    """Pending 메시지 재할당.

    XAUTOCLAIM을 사용하여 오래된 Pending 메시지를 현재 Consumer로 재할당.
    처리 중 Consumer가 죽은 경우 복구.
    """

    def __init__(
        self,
        redis_client: "aioredis.Redis",
        processor: EventProcessor,
        consumer_group: str,
        consumer_name: str,
        stream_prefix: str = "scan:events",
        shard_count: int = 4,
        min_idle_ms: int = 300000,  # 5분
        interval_seconds: int = 60,
        count: int = 100,
    ) -> None:
        """초기화."""
        self._redis = redis_client
        self._processor = processor
        self._consumer_group = consumer_group
        self._consumer_name = consumer_name
        self._stream_prefix = stream_prefix
        self._shard_count = shard_count
        self._min_idle_ms = min_idle_ms
        self._interval = interval_seconds
        self._count = count
        self._shutdown = False

    async def run(self) -> None:
        """Reclaimer 메인 루프."""
        logger.info(
            "reclaimer_started",
            extra={
                "consumer_group": self._consumer_group,
                "consumer_name": self._consumer_name,
                "min_idle_ms": self._min_idle_ms,
                "interval_seconds": self._interval,
            },
        )

        EVENT_ROUTER_RECLAIMER_STATUS.set(1)

        while not self._shutdown:
            try:
                await self._reclaim_pending()
                EVENT_ROUTER_RECLAIM_RUNS.labels(result="success").inc()
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                logger.info("reclaimer_cancelled")
                break
            except Exception as e:
                EVENT_ROUTER_RECLAIM_RUNS.labels(result="error").inc()
                logger.error("reclaimer_error", extra={"error": str(e)})
                await asyncio.sleep(self._interval)

        EVENT_ROUTER_RECLAIMER_STATUS.set(0)
        logger.info("reclaimer_stopped")

    async def _reclaim_pending(self) -> None:
        """모든 shard의 Pending 메시지 재할당."""
        total_reclaimed = 0

        for shard in range(self._shard_count):
            stream_key = f"{self._stream_prefix}:{shard}"
            shard_str = str(shard)

            try:
                # XAUTOCLAIM: 오래된 Pending 메시지 재할당
                start_time = time.perf_counter()
                result = await self._redis.xautoclaim(
                    stream_key,
                    self._consumer_group,
                    self._consumer_name,
                    min_idle_time=self._min_idle_ms,
                    start_id="0-0",
                    count=self._count,
                )
                reclaim_latency = time.perf_counter() - start_time
                EVENT_ROUTER_RECLAIM_LATENCY.labels(shard=shard_str).observe(reclaim_latency)

                # result: (next_start_id, [(msg_id, data), ...], deleted_ids)
                if len(result) >= 2:
                    messages = result[1]
                    if messages:
                        reclaimed_count = await self._process_reclaimed(stream_key, messages)
                        total_reclaimed += reclaimed_count
                        EVENT_ROUTER_RECLAIM_MESSAGES.labels(shard=shard_str).inc(reclaimed_count)

            except Exception as e:
                if "NOGROUP" in str(e):
                    # Consumer Group이 없음 (아직 생성 전)
                    continue
                logger.error(
                    "xautoclaim_error",
                    extra={"stream": stream_key, "error": str(e)},
                )

        if total_reclaimed > 0:
            logger.info(
                "reclaim_completed",
                extra={"total_reclaimed": total_reclaimed},
            )

    async def _process_reclaimed(
        self,
        stream_key: str,
        messages: list[tuple[bytes | str, dict[bytes | str, bytes | str]]],
    ) -> int:
        """재할당된 메시지 처리."""
        processed_count = 0

        for msg_id, data in messages:
            if isinstance(msg_id, bytes):
                msg_id = msg_id.decode()

            event = self._parse_event(data)

            try:
                # 이벤트 처리 (멱등성 보장되므로 안전)
                await self._processor.process_event(event)
                processed_count += 1
            except Exception as e:
                logger.error(
                    "reclaim_process_error",
                    extra={
                        "stream": stream_key,
                        "msg_id": msg_id,
                        "error": str(e),
                    },
                )

            # ACK
            try:
                await self._redis.xack(
                    stream_key,
                    self._consumer_group,
                    msg_id,
                )
            except Exception as e:
                logger.error(
                    "reclaim_xack_error",
                    extra={
                        "stream": stream_key,
                        "msg_id": msg_id,
                        "error": str(e),
                    },
                )

        logger.debug(
            "reclaim_batch_processed",
            extra={
                "stream": stream_key,
                "processed_count": processed_count,
            },
        )

        return processed_count

    def _parse_event(self, data: dict[bytes | str, bytes | str]) -> dict[str, Any]:
        """Redis 메시지 파싱."""
        event: dict[str, Any] = {}

        for k, v in data.items():
            key = k.decode() if isinstance(k, bytes) else k
            value = v.decode() if isinstance(v, bytes) else v
            event[key] = value

        # result JSON 파싱
        if "result" in event and isinstance(event["result"], str) and event["result"]:
            try:
                event["result"] = json.loads(event["result"])
            except json.JSONDecodeError:
                pass

        # seq, progress 정수 변환
        for int_field in ("seq", "progress"):
            if int_field in event:
                try:
                    event[int_field] = int(event[int_field])
                except (ValueError, TypeError):
                    pass

        return event

    async def shutdown(self) -> None:
        """Reclaimer 종료."""
        self._shutdown = True
        logger.info("reclaimer_shutdown_requested")
