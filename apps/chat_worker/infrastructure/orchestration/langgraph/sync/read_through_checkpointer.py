"""ReadThroughCheckpointer - Redis Primary + PostgreSQL Cold Start Fallback.

Redis miss 시 PostgreSQL에서 읽어 Redis에 promote (LRU write-back).

Temporal Locality (시간적 지역성) 원리:
- 최근 참조된 데이터는 가까운 미래에 다시 참조될 가능성이 높음
- Redis TTL 만료 후 재접속한 사용자의 checkpoint를 PG에서 읽어 Redis에 적재
- 이후 동일 세션의 연속 요청은 Redis에서 직접 서빙 (hot path 복원)

아키텍처:
```
graph.ainvoke() → ReadThroughCheckpointer
                    ├─ aget_tuple(): Redis hit → 즉시 반환
                    │                Redis miss → PG read → Redis write-back → 반환
                    ├─ aput(): SyncableRedisSaver (변경 없음)
                    └─ alist(): Redis first, PG fallback
```
"""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator, Optional, Sequence

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)

logger = logging.getLogger(__name__)


class ReadThroughCheckpointer(BaseCheckpointSaver):
    """Redis Primary + PostgreSQL Read-Through Checkpointer.

    Write path: SyncableRedisSaver (Redis + sync queue)
    Read path:  Redis → miss → PostgreSQL → Redis promote (LRU)

    Worker의 primary checkpointer로 사용.
    PostgreSQL pool은 read-only, 소규모 (max_size=2).
    Cold start (Redis TTL 만료 세션)에만 PG 접근.
    """

    def __init__(
        self,
        redis_saver: Any,  # SyncableRedisSaver
        pg_saver: Any,  # AsyncPostgresSaver (read-only)
    ):
        super().__init__()
        self._redis_saver = redis_saver
        self._pg_saver = pg_saver
        self._promote_count = 0
        self._miss_count = 0

    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """Checkpoint 조회 (Read-Through with LRU promotion).

        1. Redis에서 조회 (hot path, ~1ms)
        2. Redis miss → PostgreSQL에서 조회 (cold start, ~10-50ms)
        3. PG hit → Redis에 promote (write-back, 이후 요청은 Redis에서 서빙)
        """
        # 1. Redis 조회 (primary)
        result = await self._redis_saver.aget_tuple(config)
        if result is not None:
            return result

        # 2. PostgreSQL fallback (cold start) with stale connection retry
        if self._pg_saver is None:
            return None

        pg_result = await self._aget_tuple_pg_with_retry(config)
        if pg_result is None:
            self._miss_count += 1
            self._record_cold_miss()
            return None

        # 3. Redis에 promote (LRU write-back, sync queue bypass)
        # 시간적 지역성: 방금 참조된 데이터는 곧 다시 참조될 가능성 높음
        # aput_no_sync: 이미 PG에 존재하는 데이터이므로 sync queue 불필요
        promote_start = time.monotonic()
        try:
            await self._redis_saver.aput_no_sync(
                config=pg_result.config,
                checkpoint=pg_result.checkpoint,
                metadata=pg_result.metadata,
                new_versions={},
            )

            # Channel writes도 promote
            if pg_result.pending_writes:
                for task_id, channel, value in pg_result.pending_writes:
                    await self._redis_saver.aput_writes(
                        config=pg_result.config,
                        writes=[(channel, value)],
                        task_id=task_id,
                    )

            self._promote_count += 1
            promote_duration = time.monotonic() - promote_start
            self._record_promote(promote_duration)
            thread_id = config.get("configurable", {}).get("thread_id", "unknown")
            logger.info(
                "Checkpoint promoted PG→Redis (thread_id=%s, duration=%.3fs, total=%d)",
                thread_id,
                promote_duration,
                self._promote_count,
            )
        except Exception:
            # Promote 실패해도 PG 결과는 반환 (graceful degradation)
            logger.warning("Failed to promote checkpoint to Redis", exc_info=True)

        return pg_result

    async def _aget_tuple_pg_with_retry(
        self, config: RunnableConfig, max_retries: int = 1
    ) -> Optional[CheckpointTuple]:
        """PG aget_tuple with retry on stale connection.

        Cloud 환경에서 PG 서버가 idle 커넥션을 먼저 닫는 경우,
        pool이 dead 커넥션을 반환할 수 있음. 1회 재시도로 복구.
        """
        import asyncio

        from psycopg import OperationalError

        for attempt in range(max_retries + 1):
            try:
                return await self._pg_saver.aget_tuple(config)
            except OperationalError as e:
                if attempt < max_retries:
                    logger.warning(
                        "PG stale connection, retrying (attempt=%d/%d): %s",
                        attempt + 1,
                        max_retries + 1,
                        str(e),
                    )
                    await asyncio.sleep(0.5)
                else:
                    logger.error(
                        "PG aget_tuple failed after retries, treating as miss: %s",
                        str(e),
                    )
                    return None

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Checkpoint 저장 (SyncableRedisSaver에 위임)."""
        return await self._redis_saver.aput(config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Channel writes 저장 (SyncableRedisSaver에 위임)."""
        await self._redis_saver.aput_writes(config, writes, task_id, task_path)

    async def alist(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """Checkpoint 목록 조회.

        Redis에서 먼저 조회, 결과 없으면 PostgreSQL fallback.
        alist는 히스토리 조회용이므로 promote하지 않음.
        """
        has_results = False
        async for item in self._redis_saver.alist(
            config, filter=filter, before=before, limit=limit
        ):
            has_results = True
            yield item

        # Redis에 결과 없으면 PG fallback
        if not has_results and self._pg_saver is not None:
            async for item in self._pg_saver.alist(
                config, filter=filter, before=before, limit=limit
            ):
                yield item

    async def asetup(self) -> None:
        """초기화 (Redis saver는 이미 setup 완료 상태)."""
        pass

    def get_stats(self) -> dict[str, int]:
        """Promote/miss 통계 반환 (모니터링용)."""
        return {
            "promote_count": self._promote_count,
            "miss_count": self._miss_count,
        }

    def _record_promote(self, duration: float) -> None:
        """Prometheus promote 메트릭 기록."""
        try:
            from chat_worker.infrastructure.metrics import (
                CHAT_CHECKPOINT_PROMOTES_TOTAL,
                CHAT_CHECKPOINT_PROMOTE_DURATION,
            )

            CHAT_CHECKPOINT_PROMOTES_TOTAL.inc()
            CHAT_CHECKPOINT_PROMOTE_DURATION.observe(duration)
        except Exception:
            pass  # 메트릭 실패는 무시

    def _record_cold_miss(self) -> None:
        """Prometheus cold miss 메트릭 기록."""
        try:
            from chat_worker.infrastructure.metrics import (
                CHAT_CHECKPOINT_COLD_MISSES_TOTAL,
            )

            CHAT_CHECKPOINT_COLD_MISSES_TOTAL.inc()
        except Exception:
            pass  # 메트릭 실패는 무시

    async def close(self) -> None:
        """리소스 정리."""
        # Redis saver 정리
        if hasattr(self._redis_saver, "__aexit__"):
            await self._redis_saver.__aexit__(None, None, None)

        # PG saver pool 정리
        if self._pg_saver and hasattr(self._pg_saver, "conn"):
            pool = self._pg_saver.conn
            if hasattr(pool, "close"):
                await pool.close()

        logger.info(
            "ReadThroughCheckpointer closed (promotes=%d, misses=%d)",
            self._promote_count,
            self._miss_count,
        )
