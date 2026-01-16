"""Event Router Consumer.

Redis Streams Consumer Group을 사용하여 이벤트 소비.
멀티 도메인 지원: scan:events, chat:events 동시 구독.

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
    EVENT_ROUTER_ACTIVE_SHARDS,
    EVENT_ROUTER_CONSUMER_STATUS,
    EVENT_ROUTER_XACK_TOTAL,
    EVENT_ROUTER_XREADGROUP_BATCH_SIZE,
    EVENT_ROUTER_XREADGROUP_LATENCY,
    EVENT_ROUTER_XREADGROUP_TOTAL,
)

from .processor import EventProcessor

logger = logging.getLogger(__name__)


class StreamConsumer:
    """Redis Streams Consumer.

    Consumer Group을 사용하여 다수의 shard에서 이벤트를 소비.
    멀티 도메인 지원: scan:events, chat:events 동시 구독.
    XREADGROUP으로 메시지를 읽고 처리 후 XACK.
    """

    def __init__(
        self,
        redis_client: "aioredis.Redis",
        processor: EventProcessor,
        consumer_group: str,
        consumer_name: str,
        stream_configs: list[tuple[str, int]] | None = None,
        block_ms: int = 5000,
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
            block_ms: XREADGROUP 블로킹 시간
            count: 한 번에 읽을 최대 메시지 수
        """
        self._redis = redis_client
        self._processor = processor
        self._consumer_group = consumer_group
        self._consumer_name = consumer_name
        # 기본값: scan:events 4 shards
        self._stream_configs = stream_configs or [("scan:events", 4)]
        self._block_ms = block_ms
        self._count = count
        self._shutdown = False
        self._streams: dict[str, str] = {}
        self._total_shards = sum(count for _, count in self._stream_configs)

    async def setup(self) -> None:
        """Consumer Group 생성 (없으면 생성).

        멀티 도메인: 모든 prefix의 모든 shard에 대해 Consumer Group 생성.
        """
        for prefix, shard_count in self._stream_configs:
            for shard in range(shard_count):
                stream_key = f"{prefix}:{shard}"
                try:
                    # Consumer Group 생성 (이미 있으면 예외 무시)
                    await self._redis.xgroup_create(
                        stream_key,
                        self._consumer_group,
                        id="0",  # 처음부터 읽기
                        mkstream=True,  # Stream 없으면 생성
                    )
                    logger.info(
                        "consumer_group_created",
                        extra={
                            "stream": stream_key,
                            "group": self._consumer_group,
                            "domain": prefix.split(":")[0],
                        },
                    )
                except Exception as e:
                    if "BUSYGROUP" in str(e):
                        # 이미 존재
                        logger.debug(
                            "consumer_group_exists",
                            extra={"stream": stream_key, "group": self._consumer_group},
                        )
                    else:
                        logger.error(
                            "consumer_group_create_error",
                            extra={"stream": stream_key, "error": str(e)},
                        )
                        raise

                # XREADGROUP에서 사용할 streams dict
                self._streams[stream_key] = ">"

        logger.info(
            "multi_domain_consumer_setup_complete",
            extra={
                "stream_configs": self._stream_configs,
                "total_streams": len(self._streams),
            },
        )

    async def consume(self) -> None:
        """메인 Consumer 루프.

        멀티 도메인: scan:events, chat:events 동시 소비.
        """
        logger.info(
            "consumer_started",
            extra={
                "consumer_group": self._consumer_group,
                "consumer_name": self._consumer_name,
                "stream_configs": self._stream_configs,
                "total_shards": self._total_shards,
            },
        )

        EVENT_ROUTER_CONSUMER_STATUS.set(1)
        EVENT_ROUTER_ACTIVE_SHARDS.set(self._total_shards)

        while not self._shutdown:
            try:
                # XREADGROUP: 모든 shard에서 읽기
                start_time = time.perf_counter()
                events = await self._redis.xreadgroup(
                    groupname=self._consumer_group,
                    consumername=self._consumer_name,
                    streams=self._streams,
                    count=self._count,
                    block=self._block_ms,
                )
                xread_latency = time.perf_counter() - start_time
                EVENT_ROUTER_XREADGROUP_LATENCY.observe(xread_latency)

                if not events:
                    EVENT_ROUTER_XREADGROUP_TOTAL.labels(result="empty").inc()
                    continue

                EVENT_ROUTER_XREADGROUP_TOTAL.labels(result="success").inc()

                for stream_name, messages in events:
                    if isinstance(stream_name, bytes):
                        stream_name = stream_name.decode()

                    EVENT_ROUTER_XREADGROUP_BATCH_SIZE.observe(len(messages))

                    for msg_id, data in messages:
                        if isinstance(msg_id, bytes):
                            msg_id = msg_id.decode()

                        # 이벤트 파싱
                        event = self._parse_event(data)

                        # 이벤트 처리 (stream_name 전달하여 도메인별 state prefix 결정)
                        try:
                            await self._processor.process_event(
                                event, stream_name=stream_name
                            )
                        except Exception as e:
                            logger.error(
                                "process_event_error",
                                extra={
                                    "stream": stream_name,
                                    "msg_id": msg_id,
                                    "error": str(e),
                                },
                            )
                            # 처리 실패해도 ACK (재처리는 reclaimer가 담당)
                            # 또는 Pending 상태로 유지하려면 continue

                        # ACK
                        try:
                            await self._redis.xack(
                                stream_name,
                                self._consumer_group,
                                msg_id,
                            )
                            EVENT_ROUTER_XACK_TOTAL.labels(result="success").inc()
                        except Exception as e:
                            EVENT_ROUTER_XACK_TOTAL.labels(result="error").inc()
                            logger.error(
                                "xack_error",
                                extra={
                                    "stream": stream_name,
                                    "msg_id": msg_id,
                                    "error": str(e),
                                },
                            )

            except asyncio.CancelledError:
                logger.info("consumer_cancelled")
                break
            except Exception as e:
                EVENT_ROUTER_XREADGROUP_TOTAL.labels(result="error").inc()
                logger.error("consumer_error", extra={"error": str(e)})
                await asyncio.sleep(1)

        EVENT_ROUTER_CONSUMER_STATUS.set(0)
        logger.info("consumer_stopped")

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
        """Consumer 종료."""
        self._shutdown = True
        logger.info("consumer_shutdown_requested")
