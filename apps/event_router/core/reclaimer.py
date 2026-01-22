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
        stream_configs: list[tuple[str, int]] | None = None,
        min_idle_ms: int = 300000,  # 5분
        interval_seconds: int = 60,
        count: int = 100,
    ) -> None:
        """초기화.

        Args:
            redis_client: Redis 클라이언트
            processor: 이벤트 처리기
            consumer_group: Consumer Group 이름
            consumer_name: Consumer 이름
            stream_configs: [(prefix, shard_count), ...] 형태
                예: [("scan:events", 4), ("chat:events", 4)]
            min_idle_ms: Pending 메시지 최소 대기 시간 (기본 5분)
            interval_seconds: Reclaim 주기 (기본 60초)
            count: 한 번에 처리할 최대 메시지 수
        """
        self._redis = redis_client
        self._processor = processor
        self._consumer_group = consumer_group
        self._consumer_name = consumer_name
        # 멀티 도메인 지원: Consumer와 동일한 구조
        self._stream_configs = stream_configs or [("scan:events", 4)]
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
                "stream_configs": self._stream_configs,
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
        """모든 도메인의 모든 shard에서 Pending 메시지 재할당.

        각 도메인을 병렬로 처리하여 한 도메인의 지연이 다른 도메인에 영향 없음.
        """
        # 도메인별 병렬 처리
        tasks = [
            self._reclaim_domain(prefix, shard_count)
            for prefix, shard_count in self._stream_configs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 결과 집계
        total_reclaimed = 0
        for result in results:
            if isinstance(result, Exception):
                logger.error("reclaim_domain_error", extra={"error": str(result)})
            elif isinstance(result, int):
                total_reclaimed += result

        if total_reclaimed > 0:
            logger.info(
                "reclaim_completed",
                extra={"total_reclaimed": total_reclaimed},
            )

    async def _reclaim_domain(self, prefix: str, shard_count: int) -> int:
        """단일 도메인의 모든 shard에서 Pending 메시지 재할당."""
        domain = prefix.split(":")[0]
        domain_reclaimed = 0

        for shard in range(shard_count):
            stream_key = f"{prefix}:{shard}"
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
                EVENT_ROUTER_RECLAIM_LATENCY.labels(domain=domain, shard=shard_str).observe(
                    reclaim_latency
                )

                # result: (next_start_id, [(msg_id, data), ...], deleted_ids)
                if len(result) >= 2:
                    messages = result[1]
                    if messages:
                        reclaimed_count = await self._process_reclaimed(stream_key, messages)
                        domain_reclaimed += reclaimed_count
                        EVENT_ROUTER_RECLAIM_MESSAGES.labels(domain=domain, shard=shard_str).inc(
                            reclaimed_count
                        )

            except Exception as e:
                if "NOGROUP" in str(e):
                    # Consumer Group이 없음 (아직 생성 전)
                    continue
                logger.error(
                    "xautoclaim_error",
                    extra={"stream": stream_key, "domain": domain, "error": str(e)},
                )

        return domain_reclaimed

    async def _process_reclaimed(
        self,
        stream_key: str,
        messages: list[tuple[bytes | str, dict[bytes | str, bytes | str]]],
    ) -> int:
        """재할당된 메시지 처리.

        Consumer와 동일한 패턴:
        - stream_id 주입 (SSE Gateway 중복 필터링용)
        - stream_name 전달 (도메인별 state prefix 결정)
        - 실패 시 ACK 스킵 (다음 reclaim 주기에 재시도)
        """
        processed_count = 0

        for msg_id, data in messages:
            if isinstance(msg_id, bytes):
                msg_id = msg_id.decode()

            event = self._parse_event(data)

            # Stream ID 주입 (Consumer와 동일)
            # SSE Gateway에서 중복 필터링에 사용
            event["stream_id"] = msg_id

            # 이벤트 처리 (stream_key 전달하여 도메인별 state prefix 결정)
            # 실패 시 ACK 하지 않음 → 다음 reclaim 주기에 재시도
            try:
                success = await self._processor.process_event(event, stream_name=stream_key)
                if not success:
                    # Pub/Sub 발행 실패 - 다음 reclaim 주기에 재시도
                    logger.warning(
                        "reclaim_pubsub_failed",
                        extra={
                            "stream": stream_key,
                            "msg_id": msg_id,
                            "job_id": event.get("job_id"),
                        },
                    )
                    continue  # ACK 스킵
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
                # 처리 실패 - 다음 reclaim 주기에 재시도
                continue  # ACK 스킵

            # 성공한 경우만 ACK
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
