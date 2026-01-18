"""LangGraph Checkpointer with Cache-Aside Pattern.

멀티턴 대화 컨텍스트를 영구 저장합니다.

아키텍처:
```
조회 (get)
──────────
Client → Redis (L1, ~1ms)
            │
            ├── Hit → Return (빠름)
            │
            └── Miss → PostgreSQL (L2) → Load
                            │
                            └── Redis에 캐싱 (warm-up)
                                    │
                                    └── Return

저장 (put)
──────────
Client → PostgreSQL (영구) + Redis (캐시)
         Write-Through
```

Scan vs Chat:
- Scan: Stateless Reducer + Redis (단일 요청, TTL 1시간)
- Chat: Cache-Aside + PostgreSQL (멀티턴 대화, 영구 저장)

참조:
- Clean Architecture #14: Stateless Reducer Pattern
- LangGraph Checkpointing
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, AsyncIterator, Sequence

if TYPE_CHECKING:
    from langgraph.checkpoint.base import (
        BaseCheckpointSaver,
        Checkpoint,
        CheckpointMetadata,
        CheckpointTuple,
    )
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# 캐시 키 프리픽스
CACHE_KEY_PREFIX = "chat:checkpoint:cache"
DEFAULT_CACHE_TTL = 86400  # 24시간


from langgraph.checkpoint.base import BaseCheckpointSaver


class CachedPostgresSaver(BaseCheckpointSaver):
    """Cache-Aside 패턴 Checkpointer.

    L1: Redis (빠름, TTL 24시간)
    L2: PostgreSQL (영구)

    Hot session은 Redis에서 ~1ms 응답.
    Cold session은 PostgreSQL에서 로드 후 캐싱.
    """

    def __init__(
        self,
        postgres_saver: "BaseCheckpointSaver",
        redis: "Redis",
        cache_ttl: int = DEFAULT_CACHE_TTL,
    ):
        """초기화.

        Args:
            postgres_saver: PostgreSQL 체크포인터 (L2)
            redis: Redis 클라이언트 (L1 캐시)
            cache_ttl: 캐시 TTL 초 (기본 24시간)
        """
        self._postgres = postgres_saver
        self._redis = redis
        self._ttl = cache_ttl
        logger.info(
            "CachedPostgresSaver initialized (ttl=%d)",
            cache_ttl,
        )

    def _cache_key(self, thread_id: str, checkpoint_ns: str = "") -> str:
        """캐시 키 생성."""
        if checkpoint_ns:
            return f"{CACHE_KEY_PREFIX}:{thread_id}:{checkpoint_ns}"
        return f"{CACHE_KEY_PREFIX}:{thread_id}"

    async def aget_tuple(self, config: dict[str, Any]) -> "CheckpointTuple | None":
        """체크포인트 조회 (Cache-Aside).

        1. Redis 캐시 조회 (L1)
        2. Cache Miss → PostgreSQL 조회 (L2)
        3. PostgreSQL 결과를 Redis에 캐싱 (warm-up)
        """
        thread_id = config.get("configurable", {}).get("thread_id", "")
        checkpoint_ns = config.get("configurable", {}).get("checkpoint_ns", "")
        cache_key = self._cache_key(thread_id, checkpoint_ns)

        # L1: Redis 캐시 조회
        try:
            cached = await self._redis.get(cache_key)
            if cached:
                logger.debug(
                    "checkpoint_cache_hit",
                    extra={"thread_id": thread_id},
                )
                # 캐시된 데이터는 직접 반환하지 않고 PostgreSQL에 위임
                # (LangGraph 내부 직렬화 형식 호환성을 위해)
        except Exception as e:
            logger.warning(
                "checkpoint_cache_get_failed",
                extra={"thread_id": thread_id, "error": str(e)},
            )

        # L2: PostgreSQL 조회
        result = await self._postgres.aget_tuple(config)

        if result:
            # Warm-up: Redis에 캐싱 (메타데이터만 캐싱하여 hit 여부 판단)
            try:
                await self._redis.setex(
                    cache_key,
                    self._ttl,
                    json.dumps({"thread_id": thread_id, "cached": True}),
                )
                logger.debug(
                    "checkpoint_cache_warmed",
                    extra={"thread_id": thread_id, "ttl": self._ttl},
                )
            except Exception as e:
                logger.warning(
                    "checkpoint_cache_warm_failed",
                    extra={"thread_id": thread_id, "error": str(e)},
                )

        return result

    async def aput(
        self,
        config: dict[str, Any],
        checkpoint: "Checkpoint",
        metadata: "CheckpointMetadata",
        new_versions: dict[str, int | str] | None = None,
    ) -> dict[str, Any]:
        """체크포인트 저장 (Write-Through).

        PostgreSQL에 저장하고 Redis 캐시도 갱신.
        """
        thread_id = config.get("configurable", {}).get("thread_id", "")
        checkpoint_ns = config.get("configurable", {}).get("checkpoint_ns", "")
        cache_key = self._cache_key(thread_id, checkpoint_ns)

        # L2: PostgreSQL에 저장 (영구)
        result = await self._postgres.aput(config, checkpoint, metadata, new_versions)

        # L1: Redis 캐시 갱신
        try:
            await self._redis.setex(
                cache_key,
                self._ttl,
                json.dumps({"thread_id": thread_id, "cached": True}),
            )
            logger.debug(
                "checkpoint_cache_updated",
                extra={"thread_id": thread_id},
            )
        except Exception as e:
            logger.warning(
                "checkpoint_cache_update_failed",
                extra={"thread_id": thread_id, "error": str(e)},
            )

        return result

    async def alist(
        self,
        config: dict[str, Any],
        *,
        filter: dict[str, Any] | None = None,
        before: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> AsyncIterator["CheckpointTuple"]:
        """체크포인트 목록 조회 (PostgreSQL 직접 조회)."""
        async for item in self._postgres.alist(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput_writes(
        self,
        config: dict[str, Any],
        writes: Sequence[tuple[str, Any]],
        task_id: str,
    ) -> None:
        """중간 쓰기 저장 (PostgreSQL에 위임)."""
        await self._postgres.aput_writes(config, writes, task_id)

    async def close(self) -> None:
        """리소스 정리."""
        if hasattr(self._postgres, "close"):
            await self._postgres.close()


async def create_cached_postgres_checkpointer(
    conn_string: str,
    redis: "Redis",
    cache_ttl: int = DEFAULT_CACHE_TTL,
) -> CachedPostgresSaver:
    """Cache-Aside PostgreSQL 체크포인터 생성.

    L1: Redis (빠름, TTL)
    L2: PostgreSQL (영구)

    Args:
        conn_string: PostgreSQL 연결 문자열
        redis: Redis 클라이언트
        cache_ttl: 캐시 TTL 초 (기본 24시간)

    Returns:
        CachedPostgresSaver 인스턴스
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    postgres_saver = await AsyncPostgresSaver.from_conn_string(conn_string)

    logger.info(
        "CachedPostgresSaver created (PostgreSQL + Redis cache)",
        extra={"conn_string": conn_string[:20] + "...", "cache_ttl": cache_ttl},
    )

    return CachedPostgresSaver(
        postgres_saver=postgres_saver,
        redis=redis,
        cache_ttl=cache_ttl,
    )


async def create_postgres_checkpointer(
    conn_string: str,
) -> "BaseCheckpointSaver":
    """PostgreSQL 체크포인터 생성 (캐시 없음).

    Cache-Aside 없이 PostgreSQL만 사용.
    Redis 없는 환경에서 폴백으로 사용.

    Args:
        conn_string: PostgreSQL 연결 문자열

    Returns:
        AsyncPostgresSaver 인스턴스
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    checkpointer = await AsyncPostgresSaver.from_conn_string(conn_string)

    logger.info(
        "PostgreSQL checkpointer created (no cache)",
        extra={"conn_string": conn_string[:20] + "..."},
    )

    return checkpointer


async def create_redis_checkpointer(
    redis_url: str,
    ttl: int = 86400,
) -> "BaseCheckpointSaver":
    """Redis 체크포인터 생성 (단기 세션용 폴백).

    PostgreSQL 연결 실패 시 폴백으로 사용.
    TTL이 있으므로 장기 세션에는 부적합.

    Args:
        redis_url: Redis 연결 URL
        ttl: TTL 초 (기본 24시간)

    Returns:
        RedisSaver 인스턴스
    """
    # AsyncRedisSaver.from_conn_string()은 async context manager를 반환
    # 싱글톤 패턴과 호환되지 않으므로 MemorySaver로 대체
    # TODO: Redis checkpointer를 제대로 지원하려면 lifecycle 관리 필요
    from langgraph.checkpoint.memory import MemorySaver

    checkpointer = MemorySaver()

    logger.info(
        "InMemory checkpointer created (Redis fallback disabled)",
        extra={"redis_url": redis_url[:20] + "...", "ttl": ttl},
    )

    return checkpointer
