"""Task state management with Redis.

Redis를 사용하여 태스크의 진행 상태를 관리합니다.
프론트엔드 UI와 연동하여 실시간 프로그레스를 표시할 수 있습니다.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import redis.asyncio as aioredis

from domains._shared.taskqueue.config import get_celery_settings

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Task execution status."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStep(str, Enum):
    """Pipeline step indicator for UI progress."""

    PENDING = "pending"
    SCAN = "scan"  # Vision (GPT)
    ANALYZE = "analyze"  # Rule-based RAG
    ANSWER = "answer"  # Answer generation (GPT)
    COMPLETE = "complete"


# Step to progress mapping
STEP_PROGRESS = {
    TaskStep.PENDING: 0,
    TaskStep.SCAN: 15,
    TaskStep.ANALYZE: 50,
    TaskStep.ANSWER: 75,
    TaskStep.COMPLETE: 100,
}


@dataclass
class TaskState:
    """Task state data structure stored in Redis.

    이 클래스는 Redis Hash로 저장되며, 프론트엔드 폴링 또는 SSE를 통해
    실시간으로 조회될 수 있습니다.
    """

    task_id: str
    user_id: str
    status: TaskStatus = TaskStatus.QUEUED
    step: TaskStep = TaskStep.PENDING
    progress: int = 0

    # Request data
    image_url: str | None = None

    # Partial results (단계별 결과)
    partial_result: dict[str, Any] = field(default_factory=dict)

    # Final result (완료 후)
    result: dict[str, Any] | None = None

    # Error info (실패 시)
    error: str | None = None
    error_code: str | None = None

    # Reward status (분리 추적)
    reward_status: str = "pending"  # pending | processing | granted | failed | queued
    reward_task_id: str | None = None

    # Timing
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Metadata (duration 등)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Redis storage."""
        data = asdict(self)
        # Enum을 문자열로 변환
        data["status"] = self.status.value
        data["step"] = self.step.value
        # dict/None 필드는 JSON 문자열로 변환
        data["partial_result"] = json.dumps(data["partial_result"])
        data["result"] = json.dumps(data["result"]) if data["result"] else ""
        data["metadata"] = json.dumps(data["metadata"])
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskState:
        """Create TaskState from Redis hash data."""
        # 문자열을 Enum으로 변환
        data["status"] = TaskStatus(data.get("status", "queued"))
        data["step"] = TaskStep(data.get("step", "pending"))
        data["progress"] = int(data.get("progress", 0))

        # JSON 문자열을 dict로 변환
        partial = data.get("partial_result", "{}")
        data["partial_result"] = json.loads(partial) if partial else {}

        result = data.get("result", "")
        data["result"] = json.loads(result) if result else None

        metadata = data.get("metadata", "{}")
        data["metadata"] = json.loads(metadata) if metadata else {}

        return cls(**data)


class TaskStateManager:
    """Redis-based task state manager.

    Singleton 패턴으로 관리되며, 비동기 Redis 연결을 사용합니다.
    """

    _instance: "TaskStateManager | None" = None
    _redis: aioredis.Redis | None = None

    def __new__(cls) -> "TaskStateManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            settings = get_celery_settings()
            self._redis = aioredis.from_url(
                settings.state_redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    def _key(self, task_id: str) -> str:
        """Generate Redis key for task state."""
        return f"task:{task_id}"

    async def create(self, state: TaskState) -> None:
        """Create new task state in Redis."""
        redis = await self._get_redis()
        settings = get_celery_settings()

        key = self._key(state.task_id)
        await redis.hset(key, mapping=state.to_dict())
        await redis.expire(key, settings.state_ttl_seconds)

        logger.debug(f"Created task state: {state.task_id}")

    async def update(
        self,
        task_id: str,
        *,
        status: TaskStatus | None = None,
        step: TaskStep | None = None,
        progress: int | None = None,
        partial_result: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        error_code: str | None = None,
        reward_status: str | None = None,
        reward_task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Update task state fields."""
        redis = await self._get_redis()
        key = self._key(task_id)

        updates: dict[str, Any] = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        if status is not None:
            updates["status"] = status.value
        if step is not None:
            updates["step"] = step.value
            # Auto-calculate progress if not provided
            if progress is None:
                updates["progress"] = STEP_PROGRESS.get(step, 0)
        if progress is not None:
            updates["progress"] = progress
        if partial_result is not None:
            updates["partial_result"] = json.dumps(partial_result)
        if result is not None:
            updates["result"] = json.dumps(result)
        if error is not None:
            updates["error"] = error
        if error_code is not None:
            updates["error_code"] = error_code
        if reward_status is not None:
            updates["reward_status"] = reward_status
        if reward_task_id is not None:
            updates["reward_task_id"] = reward_task_id
        if metadata is not None:
            # Merge with existing metadata
            existing = await redis.hget(key, "metadata")
            existing_meta = json.loads(existing) if existing else {}
            existing_meta.update(metadata)
            updates["metadata"] = json.dumps(existing_meta)

        await redis.hset(key, mapping=updates)
        logger.debug(f"Updated task state: {task_id}, fields={list(updates.keys())}")

    async def get(self, task_id: str) -> TaskState | None:
        """Get task state by ID."""
        redis = await self._get_redis()
        key = self._key(task_id)

        data = await redis.hgetall(key)
        if not data:
            return None

        return TaskState.from_dict(data)

    async def delete(self, task_id: str) -> None:
        """Delete task state."""
        redis = await self._get_redis()
        await redis.delete(self._key(task_id))
        logger.debug(f"Deleted task state: {task_id}")

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


# Global instance
_state_manager: TaskStateManager | None = None


def get_state_manager() -> TaskStateManager:
    """Get TaskStateManager singleton instance."""
    global _state_manager
    if _state_manager is None:
        _state_manager = TaskStateManager()
    return _state_manager


async def close_state_manager() -> None:
    """Close state manager connection (for shutdown)."""
    global _state_manager
    if _state_manager:
        await _state_manager.close()
        _state_manager = None
