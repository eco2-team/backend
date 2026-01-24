"""PlainAsyncRedisSaver - Standard Redis checkpointer (no RediSearch/RedisJSON).

langgraph-checkpoint-redis는 Redis Stack (RediSearch + RedisJSON)을 필수로 요구하지만,
프로덕션 Redis Sentinel 클러스터에는 해당 모듈이 없음.

이 구현은 표준 Redis 명령어(HSET, HGET, ZADD, EXPIRE)만 사용하여
LangGraph BaseCheckpointSaver 인터페이스를 구현.

Key 구조:
```
cp:{thread_id}:{checkpoint_ns}:{checkpoint_id}       → Hash (checkpoint + metadata)
cp:writes:{thread_id}:{checkpoint_ns}:{checkpoint_id}:{task_id} → Hash (pending writes)
cp:latest:{thread_id}:{checkpoint_ns}                → String (latest checkpoint_id)
cp:history:{thread_id}:{checkpoint_ns}               → Sorted Set (checkpoint_id by ts)
```
"""

from __future__ import annotations

import base64
import json
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
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class PlainAsyncRedisSaver(BaseCheckpointSaver):
    """LangGraph checkpointer using standard Redis commands only.

    Redis Stack 모듈(RediSearch, RedisJSON) 없이 동작.
    표준 Redis 명령어만 사용: HSET, HGET, SET, GET, ZADD, EXPIRE.

    Args:
        redis_url: Redis 연결 URL
        ttl: TTL 설정 dict (default_ttl: 분 단위)
    """

    def __init__(
        self,
        redis_url: str,
        ttl: dict[str, int] | None = None,
    ):
        super().__init__()
        self._redis_url = redis_url
        self._ttl_seconds = (ttl.get("default_ttl", 1440) * 60) if ttl else 86400
        self._redis: Optional[Redis] = None

    async def asetup(self) -> None:
        """Redis 연결 초기화 (RediSearch 불필요)."""
        self._redis = Redis.from_url(
            self._redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
            socket_timeout=10.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True,
        )
        # 연결 확인
        await self._redis.ping()
        logger.info("PlainAsyncRedisSaver connected (ttl=%ds)", self._ttl_seconds)

    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """Checkpoint 조회 (thread_id + checkpoint_ns 기준 latest).

        config에 checkpoint_id가 있으면 해당 checkpoint를 직접 조회.
        없으면 latest pointer로 최신 checkpoint 조회.
        """
        assert self._redis is not None, "Call asetup() first"

        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id", "")
        checkpoint_ns = configurable.get("checkpoint_ns", "")
        checkpoint_id = configurable.get("checkpoint_id")

        if not thread_id:
            return None

        # checkpoint_id가 없으면 latest 조회
        if not checkpoint_id:
            latest_key = self._latest_key(thread_id, checkpoint_ns)
            checkpoint_id = await self._redis.get(latest_key)
            if not checkpoint_id:
                return None

        # Checkpoint 데이터 조회
        cp_key = self._checkpoint_key(thread_id, checkpoint_ns, checkpoint_id)
        data = await self._redis.hgetall(cp_key)
        if not data:
            return None

        checkpoint = self._deserialize(data["checkpoint"])
        metadata = self._deserialize(data["metadata"]) if data.get("metadata") else {}
        parent_checkpoint_id = data.get("parent_checkpoint_id")

        # Parent config
        parent_config = None
        if parent_checkpoint_id:
            parent_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": parent_checkpoint_id,
                }
            }

        # Pending writes 조회
        pending_writes = await self._get_pending_writes(thread_id, checkpoint_ns, checkpoint_id)

        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                }
            },
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
            pending_writes=pending_writes,
        )

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Checkpoint 저장."""
        assert self._redis is not None, "Call asetup() first"

        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id", "")
        checkpoint_ns = configurable.get("checkpoint_ns", "")
        checkpoint_id = checkpoint.get("id", "")
        parent_checkpoint_id = configurable.get("checkpoint_id")

        cp_key = self._checkpoint_key(thread_id, checkpoint_ns, checkpoint_id)
        latest_key = self._latest_key(thread_id, checkpoint_ns)
        history_key = self._history_key(thread_id, checkpoint_ns)

        # Checkpoint 데이터 저장
        pipe = self._redis.pipeline()
        pipe.hset(
            cp_key,
            mapping={
                "checkpoint": self._serialize(checkpoint),
                "metadata": self._serialize(metadata),
                "parent_checkpoint_id": parent_checkpoint_id or "",
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
                "created_at": str(time.time()),
            },
        )
        pipe.expire(cp_key, self._ttl_seconds)

        # Latest pointer 업데이트
        pipe.set(latest_key, checkpoint_id, ex=self._ttl_seconds)

        # History sorted set (score = timestamp)
        ts = checkpoint.get("ts", time.time())
        score = self._ts_to_score(ts)
        pipe.zadd(history_key, {checkpoint_id: score})
        pipe.expire(history_key, self._ttl_seconds)

        await pipe.execute()

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Channel writes 저장."""
        assert self._redis is not None, "Call asetup() first"

        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id", "")
        checkpoint_ns = configurable.get("checkpoint_ns", "")
        checkpoint_id = configurable.get("checkpoint_id", "")

        writes_key = self._writes_key(thread_id, checkpoint_ns, checkpoint_id, task_id)

        pipe = self._redis.pipeline()
        for idx, (channel, value) in enumerate(writes):
            pipe.hset(
                writes_key,
                f"{idx}:{channel}",
                self._serialize({"channel": channel, "value": value}),
            )
        pipe.expire(writes_key, self._ttl_seconds)
        await pipe.execute()

    async def alist(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """Checkpoint 목록 조회 (history sorted set 기반)."""
        assert self._redis is not None, "Call asetup() first"

        if not config:
            return

        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id", "")
        checkpoint_ns = configurable.get("checkpoint_ns", "")

        if not thread_id:
            return

        history_key = self._history_key(thread_id, checkpoint_ns)

        # Sorted set에서 역순으로 checkpoint_id 목록 조회
        max_score = "+inf"
        if before:
            before_id = before.get("configurable", {}).get("checkpoint_id")
            if before_id:
                score = await self._redis.zscore(history_key, before_id)
                if score is not None:
                    max_score = f"({score}"  # exclusive

        count = limit or 10
        checkpoint_ids = await self._redis.zrevrangebyscore(
            history_key, max_score, "-inf", start=0, num=count
        )

        for cp_id in checkpoint_ids:
            cp_config: RunnableConfig = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": cp_id,
                }
            }
            result = await self.aget_tuple(cp_config)
            if result is not None:
                yield result

    async def __aenter__(self) -> "PlainAsyncRedisSaver":
        await self.asetup()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    # ─── Key helpers ──────────────────────────────────────────────

    @staticmethod
    def _checkpoint_key(thread_id: str, checkpoint_ns: str, checkpoint_id: str) -> str:
        return f"cp:{thread_id}:{checkpoint_ns}:{checkpoint_id}"

    @staticmethod
    def _writes_key(thread_id: str, checkpoint_ns: str, checkpoint_id: str, task_id: str) -> str:
        return f"cp:writes:{thread_id}:{checkpoint_ns}:{checkpoint_id}:{task_id}"

    @staticmethod
    def _latest_key(thread_id: str, checkpoint_ns: str) -> str:
        return f"cp:latest:{thread_id}:{checkpoint_ns}"

    @staticmethod
    def _history_key(thread_id: str, checkpoint_ns: str) -> str:
        return f"cp:history:{thread_id}:{checkpoint_ns}"

    @staticmethod
    def _ts_to_score(ts: Any) -> float:
        """Timestamp를 sorted set score로 변환."""
        if isinstance(ts, (int, float)):
            return float(ts)
        if isinstance(ts, str):
            try:
                from datetime import datetime

                dt = datetime.fromisoformat(ts)
                return dt.timestamp()
            except (ValueError, TypeError):
                return time.time()
        return time.time()

    def _serialize(self, obj: Any) -> str:
        """객체를 직렬화 (serde로 타입 정보 보존).

        JsonPlusSerializer는 msgpack 바이너리를 반환하므로,
        Redis string 저장을 위해 base64로 인코딩.
        포맷: "type_tag:base64_data" (예: "msgpack:xIcF9...")
        """
        type_tag, data = self.serde.dumps_typed(obj)
        encoded = base64.b64encode(data).decode("ascii")
        return f"{type_tag}:{encoded}"

    def _deserialize(self, data: str) -> Any:
        """직렬화된 문자열을 객체로 역직렬화.

        포맷 감지:
        1. "type_tag:base64_data" → serde.loads_typed (현재 포맷)
        2. legacy json.loads 폴백 (하위 호환)
        """
        # 현재 포맷: "type_tag:base64_data"
        if ":" in data:
            type_tag, encoded = data.split(":", 1)
            if type_tag in ("msgpack", "json"):
                try:
                    raw = base64.b64decode(encoded)
                    return self.serde.loads_typed((type_tag, raw))
                except Exception:
                    pass
        # Legacy 폴백: plain JSON
        try:
            return json.loads(data)
        except Exception:
            logger.warning("Checkpoint deserialize fallback to raw string: %s", data[:100])
            return data

    async def _get_pending_writes(
        self, thread_id: str, checkpoint_ns: str, checkpoint_id: str
    ) -> list[tuple[str, str, Any]]:
        """Pending writes 조회."""
        assert self._redis is not None
        pattern = self._writes_key(thread_id, checkpoint_ns, checkpoint_id, "*")
        writes: list[tuple[str, str, Any]] = []

        async for key in self._redis.scan_iter(match=pattern, count=100):
            # key에서 task_id 추출
            parts = key.rsplit(":", 1)
            task_id = parts[-1] if len(parts) > 1 else ""

            data = await self._redis.hgetall(key)
            for _field, value_json in sorted(data.items()):
                entry = self._deserialize(value_json)
                writes.append((task_id, entry["channel"], entry["value"]))

        return writes
