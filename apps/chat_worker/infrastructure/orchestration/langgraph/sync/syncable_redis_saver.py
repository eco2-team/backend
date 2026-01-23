"""SyncableRedisSaver - Redis checkpointer with sync queue.

PlainAsyncRedisSaver를 래핑하여 checkpoint 저장 시
sync queue에 이벤트를 추가합니다.
checkpoint_syncer가 이 queue를 소비하여 PostgreSQL에 동기화.

Redis List 기반 sync queue:
- Worker: LPUSH로 sync 이벤트 추가
- Syncer: BRPOP으로 이벤트 소비 (blocking, 순서 보장)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Sequence

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
)

from chat_worker.infrastructure.orchestration.langgraph.sync.plain_redis_saver import (
    PlainAsyncRedisSaver,
)

logger = logging.getLogger(__name__)

# Sync queue key
SYNC_QUEUE_KEY = "checkpoint:sync:queue"


class SyncableRedisSaver(PlainAsyncRedisSaver):
    """Redis checkpointer with sync queue for PostgreSQL synchronization.

    PlainAsyncRedisSaver (표준 Redis 명령어만 사용)에
    sync queue 기능을 추가합니다.

    Usage:
        saver = SyncableRedisSaver(
            redis_url="redis://localhost:6379/0",
            ttl={"default_ttl": 1440},
        )
        await saver.asetup()
    """

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
        stream_mode: str = "values",
    ) -> RunnableConfig:
        """Checkpoint 저장 후 sync queue에 이벤트 추가."""
        # 원본 저장
        result_config = await super().aput(config, checkpoint, metadata, new_versions, stream_mode)

        # Sync queue에 이벤트 추가 (best-effort, 실패해도 checkpoint는 저장됨)
        try:
            thread_id = config["configurable"].get("thread_id", "")
            checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
            checkpoint_id = checkpoint.get("id", "")

            event = json.dumps(
                {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                }
            )
            await self._redis.lpush(SYNC_QUEUE_KEY, event)
        except Exception:
            # Sync queue 실패는 무시 (checkpoint는 이미 Redis에 저장됨)
            # Syncer가 polling fallback으로 처리
            logger.debug("Failed to push sync event, syncer will catch up", exc_info=True)

        return result_config

    async def aput_no_sync(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
        stream_mode: str = "values",
    ) -> RunnableConfig:
        """Checkpoint 저장 (sync queue 이벤트 없이).

        Read-Through promote용: PG에서 읽은 checkpoint를 Redis에 적재할 때 사용.
        이미 PG에 존재하는 데이터이므로 sync queue에 이벤트를 추가하면
        syncer가 불필요한 PG upsert를 수행하게 됨.
        """
        return await super().aput(config, checkpoint, metadata, new_versions, stream_mode)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Channel writes 저장 (sync queue 불필요 - checkpoint에 포함됨)."""
        await super().aput_writes(config, writes, task_id, task_path)
