"""Redis Streams Consumer Client.

Event-First Architecture: chat:events:{shard}에서 done 이벤트를 소비.
Consumer Group "chat-persistence"로 Event Router와 독립적으로 동작.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Event Router와 동일한 샤딩 설정
DEFAULT_SHARD_COUNT = int(os.environ.get("CHAT_SHARD_COUNT", "4"))
STREAM_PREFIX = "chat:events"


class ChatPersistenceConsumer:
    """Chat Persistence Consumer.

    Redis Streams Consumer Group을 사용하여 done 이벤트를 소비.
    Event Router(event-router 그룹)와 별개의 그룹(chat-persistence)으로 동작.

    동일한 이벤트를 두 Consumer가 독립적으로 처리:
    - Event Router: SSE 발행
    - DB Consumer: PostgreSQL 저장
    """

    CONSUMER_GROUP = "chat-persistence"

    def __init__(
        self,
        redis: "Redis",
        consumer_name: str = "persistence-worker-0",
        shard_count: int | None = None,
        block_ms: int = 5000,
        count: int = 100,
    ) -> None:
        """초기화.

        Args:
            redis: Redis 클라이언트
            consumer_name: Consumer 이름 (Pod별로 고유)
            shard_count: Shard 수 (기본: 4)
            block_ms: XREADGROUP 블로킹 시간
            count: 한 번에 읽을 최대 메시지 수
        """
        self._redis = redis
        self._consumer_name = consumer_name
        self._shard_count = shard_count or DEFAULT_SHARD_COUNT
        self._block_ms = block_ms
        self._count = count
        self._shutdown = False
        self._streams: dict[str, str] = {}

    async def setup(self) -> None:
        """Consumer Group 생성 (없으면 생성)."""
        for shard in range(self._shard_count):
            stream_key = f"{STREAM_PREFIX}:{shard}"
            try:
                await self._redis.xgroup_create(
                    stream_key,
                    self.CONSUMER_GROUP,
                    id="0",  # 처음부터 읽기
                    mkstream=True,
                )
                logger.info(
                    "Consumer group created",
                    extra={
                        "stream": stream_key,
                        "group": self.CONSUMER_GROUP,
                    },
                )
            except Exception as e:
                if "BUSYGROUP" in str(e):
                    logger.debug(
                        "Consumer group exists",
                        extra={"stream": stream_key},
                    )
                else:
                    raise

            self._streams[stream_key] = ">"

        logger.info(
            "Chat persistence consumer setup complete",
            extra={
                "streams": list(self._streams.keys()),
                "consumer_group": self.CONSUMER_GROUP,
            },
        )

    async def consume(
        self,
        callback: Callable[[dict[str, Any]], Awaitable[bool]],
    ) -> None:
        """메인 Consumer 루프.

        Args:
            callback: 이벤트 처리 콜백 (성공 시 True 반환)
        """
        logger.info(
            "Consumer started",
            extra={
                "consumer_group": self.CONSUMER_GROUP,
                "consumer_name": self._consumer_name,
            },
        )

        while not self._shutdown:
            try:
                events = await self._redis.xreadgroup(
                    groupname=self.CONSUMER_GROUP,
                    consumername=self._consumer_name,
                    streams=self._streams,
                    count=self._count,
                    block=self._block_ms,
                )

                if not events:
                    continue

                for stream_name, messages in events:
                    if isinstance(stream_name, bytes):
                        stream_name = stream_name.decode()

                    for msg_id, data in messages:
                        if isinstance(msg_id, bytes):
                            msg_id = msg_id.decode()

                        # 이벤트 파싱
                        event = self._parse_event(data)

                        # done 이벤트만 처리 (persistence 데이터 포함)
                        if event.get("stage") != "done":
                            # done이 아닌 이벤트는 바로 ACK
                            await self._redis.xack(stream_name, self.CONSUMER_GROUP, msg_id)
                            continue

                        # persistence 데이터 확인
                        result = event.get("result", {})
                        if isinstance(result, str):
                            try:
                                result = json.loads(result)
                            except json.JSONDecodeError:
                                result = {}

                        persistence = result.get("persistence")
                        if not persistence:
                            # persistence 데이터 없으면 스킵
                            await self._redis.xack(stream_name, self.CONSUMER_GROUP, msg_id)
                            continue

                        # 콜백 실행
                        try:
                            success = await callback(persistence)
                            if success:
                                await self._redis.xack(stream_name, self.CONSUMER_GROUP, msg_id)
                                logger.debug(
                                    "Event processed and ACKed",
                                    extra={
                                        "job_id": event.get("job_id"),
                                        "msg_id": msg_id,
                                    },
                                )
                            else:
                                # 실패 시 ACK 안함 → 재시도됨
                                logger.warning(
                                    "Event processing failed, will retry",
                                    extra={"job_id": event.get("job_id")},
                                )
                        except Exception as e:
                            logger.error(
                                "Event callback error",
                                extra={
                                    "job_id": event.get("job_id"),
                                    "error": str(e),
                                },
                                exc_info=True,
                            )

            except asyncio.CancelledError:
                logger.info("Consumer cancelled")
                break
            except Exception as e:
                logger.error("Consumer error", extra={"error": str(e)})
                await asyncio.sleep(1)

        logger.info("Consumer stopped")

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

        return event

    async def shutdown(self) -> None:
        """Consumer 종료."""
        self._shutdown = True
        logger.info("Consumer shutdown requested")
