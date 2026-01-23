"""CheckpointSyncService - Redis → PostgreSQL 동기화.

Worker가 Redis에 checkpoint를 저장하면 sync queue에 이벤트가 추가됨.
이 서비스가 queue를 소비하여 PostgreSQL에 동기화.

전략:
1. BRPOP으로 sync queue에서 이벤트 대기 (blocking)
2. 배치 수집 (최대 batch_size개 또는 drain_timeout 초)
3. 각 이벤트에 대해 Redis에서 checkpoint 읽기
4. PostgreSQL에 upsert (AsyncPostgresSaver.aput)
5. 실패 시 이벤트를 DLQ로 이동

장애 복구:
- Syncer 재시작 시 queue에 남은 이벤트부터 처리
- Redis에 checkpoint가 남아있으면 언제든 sync 가능
- PostgreSQL 장애 시 queue에 이벤트 축적, PG 복구 후 일괄 처리
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from redis.asyncio import Redis

from chat_worker.infrastructure.orchestration.langgraph.sync.syncable_redis_saver import (
    SYNC_QUEUE_KEY,
)

logger = logging.getLogger(__name__)

# Dead Letter Queue (sync 실패 이벤트)
DLQ_KEY = "checkpoint:sync:dlq"
# Sync 통계
STATS_KEY = "checkpoint:sync:stats"


class CheckpointSyncService:
    """Redis → PostgreSQL checkpoint 동기화 서비스.

    Args:
        redis: Redis 클라이언트 (sync queue 소비 + checkpoint 읽기)
        redis_saver: AsyncRedisSaver (checkpoint 읽기용)
        pg_saver: AsyncPostgresSaver (checkpoint 쓰기용)
        batch_size: 배치당 최대 이벤트 수
        drain_timeout: 배치 수집 대기 시간 (초)
        max_retries: 이벤트당 최대 재시도 횟수
    """

    def __init__(
        self,
        redis: Redis,
        redis_saver: Any,  # AsyncRedisSaver
        pg_saver: Any,  # AsyncPostgresSaver
        batch_size: int = 50,
        drain_timeout: float = 2.0,
        max_retries: int = 3,
    ):
        self._redis = redis
        self._redis_saver = redis_saver
        self._pg_saver = pg_saver
        self._batch_size = batch_size
        self._drain_timeout = drain_timeout
        self._max_retries = max_retries
        self._synced_count = 0
        self._error_count = 0

    @classmethod
    async def create(
        cls,
        redis_url: str,
        postgres_url: str,
        pg_pool_min_size: int = 1,
        pg_pool_max_size: int = 5,
        batch_size: int = 50,
        drain_timeout: float = 2.0,
        checkpoint_ttl_minutes: int = 1440,
    ) -> "CheckpointSyncService":
        """팩토리 메서드.

        Args:
            redis_url: Redis 연결 URL (checkpoint 읽기 + sync queue)
            postgres_url: PostgreSQL 연결 URL (checkpoint 쓰기)
            pg_pool_min_size: PG pool 최소 연결 수
            pg_pool_max_size: PG pool 최대 연결 수
            batch_size: 배치당 최대 이벤트 수
            drain_timeout: 배치 수집 대기 시간 (초)
            checkpoint_ttl_minutes: Redis checkpoint TTL (분)

        Returns:
            CheckpointSyncService 인스턴스
        """
        from chat_worker.infrastructure.orchestration.langgraph.checkpointer import (
            create_postgres_checkpointer,
        )
        from chat_worker.infrastructure.orchestration.langgraph.sync.plain_redis_saver import (
            PlainAsyncRedisSaver,
        )

        # Redis 클라이언트 (sync queue 소비용)
        redis = Redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=10,
            socket_timeout=30.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True,
        )

        # Redis Saver (checkpoint 읽기용 - 표준 Redis 명령어만 사용)
        redis_saver = PlainAsyncRedisSaver(
            redis_url=redis_url,
            ttl={"default_ttl": checkpoint_ttl_minutes},
        )
        await redis_saver.asetup()

        # PostgreSQL Saver (checkpoint 쓰기용)
        pg_saver = await create_postgres_checkpointer(
            conn_string=postgres_url,
            pool_min_size=pg_pool_min_size,
            pool_max_size=pg_pool_max_size,
        )

        return cls(
            redis=redis,
            redis_saver=redis_saver,
            pg_saver=pg_saver,
            batch_size=batch_size,
            drain_timeout=drain_timeout,
        )

    async def run(self, stop_event: asyncio.Event) -> None:
        """메인 동기화 루프.

        stop_event가 set될 때까지 sync queue를 소비합니다.
        """
        logger.info(
            "Sync loop started (batch_size=%d, drain_timeout=%.1fs)",
            self._batch_size,
            self._drain_timeout,
        )

        while not stop_event.is_set():
            try:
                batch = await self._collect_batch(stop_event)
                if not batch:
                    continue

                synced = await self._sync_batch(batch)
                if synced > 0:
                    self._synced_count += synced
                    logger.info(
                        "Synced %d/%d checkpoints (total=%d, errors=%d)",
                        synced,
                        len(batch),
                        self._synced_count,
                        self._error_count,
                    )
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Unexpected error in sync loop")
                await asyncio.sleep(5.0)  # 에러 시 백오프

    async def _collect_batch(self, stop_event: asyncio.Event) -> list[dict]:
        """Sync queue에서 배치 수집.

        BRPOP으로 첫 이벤트를 blocking 대기 후,
        추가 이벤트를 non-blocking으로 drain.
        """
        batch: list[dict] = []

        # 첫 이벤트: blocking 대기 (timeout으로 stop_event 체크 가능)
        result = await self._redis.brpop(SYNC_QUEUE_KEY, timeout=5)
        if result is None:
            return batch  # timeout, 빈 배치 반환

        _, raw_event = result
        event = self._parse_event(raw_event)
        if event:
            batch.append(event)

        # 추가 이벤트: non-blocking drain
        deadline = time.monotonic() + self._drain_timeout
        while len(batch) < self._batch_size and time.monotonic() < deadline:
            if stop_event.is_set():
                break
            raw = await self._redis.rpop(SYNC_QUEUE_KEY)
            if raw is None:
                break
            event = self._parse_event(raw)
            if event:
                batch.append(event)

        return batch

    async def _sync_batch(self, batch: list[dict]) -> int:
        """배치 동기화 실행."""
        synced = 0

        # thread_id별로 deduplicate (동일 thread의 최신 checkpoint만 sync)
        latest: dict[tuple[str, str], dict] = {}
        for event in batch:
            key = (event["thread_id"], event["checkpoint_ns"])
            latest[key] = event  # 마지막 것이 최신

        for event in latest.values():
            try:
                success = await self._sync_one(event)
                if success:
                    synced += 1
            except Exception:
                self._error_count += 1
                logger.exception(
                    "Failed to sync checkpoint: thread_id=%s, checkpoint_id=%s",
                    event.get("thread_id"),
                    event.get("checkpoint_id"),
                )
                # DLQ로 이동
                await self._send_to_dlq(event)

        return synced

    async def _sync_one(self, event: dict) -> bool:
        """단일 checkpoint 동기화.

        Redis에서 checkpoint 읽기 → PostgreSQL에 쓰기.
        """
        thread_id = event["thread_id"]
        checkpoint_ns = event.get("checkpoint_ns", "")

        # Redis에서 checkpoint tuple 읽기
        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
            }
        }

        tuple_data = await self._redis_saver.aget_tuple(config)
        if tuple_data is None:
            # Redis에서 이미 만료됨 (TTL)
            logger.debug("Checkpoint expired in Redis: %s", thread_id)
            return False

        # PostgreSQL에 쓰기
        await self._pg_saver.aput(
            config=tuple_data.config,
            checkpoint=tuple_data.checkpoint,
            metadata=tuple_data.metadata,
            new_versions={},
        )

        # Channel writes도 동기화
        if tuple_data.pending_writes:
            for task_id, channel, value in tuple_data.pending_writes:
                await self._pg_saver.aput_writes(
                    config=tuple_data.config,
                    writes=[(channel, value)],
                    task_id=task_id,
                )

        return True

    async def _send_to_dlq(self, event: dict) -> None:
        """실패한 이벤트를 DLQ로 이동."""
        try:
            event["error_count"] = event.get("error_count", 0) + 1
            event["last_error_ts"] = time.time()
            await self._redis.lpush(DLQ_KEY, json.dumps(event))
        except Exception:
            logger.debug("Failed to send to DLQ", exc_info=True)

    def _parse_event(self, raw: str) -> dict | None:
        """이벤트 파싱."""
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Invalid sync event: %s", raw)
            return None

    async def close(self) -> None:
        """리소스 정리."""
        # Redis saver 정리
        if hasattr(self._redis_saver, "__aexit__"):
            await self._redis_saver.__aexit__(None, None, None)

        # Redis 클라이언트 정리
        await self._redis.close()

        # PostgreSQL saver는 pool을 가지고 있음
        # AsyncPostgresSaver에는 close가 없지만 pool은 있음
        if hasattr(self._pg_saver, "conn") and hasattr(self._pg_saver.conn, "close"):
            await self._pg_saver.conn.close()

        logger.info(
            "CheckpointSyncService closed (synced=%d, errors=%d)",
            self._synced_count,
            self._error_count,
        )
