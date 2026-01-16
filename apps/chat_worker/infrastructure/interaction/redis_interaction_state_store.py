"""Redis Interaction State Store - InteractionStateStorePort 구현체.

Human-in-the-Loop 상태 저장/조회.
Source of Truth(SoT) 역할 - 모든 상호작용 상태를 관리.

상태 저장 항목:
- 대기 중인 입력 요청 (HumanInputRequest)
- 파이프라인 상태 스냅샷 (재개용)
- 재개할 노드 이름

Port: application/interaction/ports/interaction_state_store.py
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.ports.interaction_state_store import InteractionStateStorePort
from chat_worker.domain import HumanInputRequest, InputType

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Redis 키 프리픽스
PENDING_REQUEST_PREFIX = "chat:interaction:pending"
PIPELINE_STATE_PREFIX = "chat:interaction:state"

# TTL (1시간)
STATE_TTL = 3600


class RedisInteractionStateStore(InteractionStateStorePort):
    """Redis 기반 상호작용 상태 저장소.

    Human-in-the-Loop 상태를 Redis에 저장/조회.
    """

    def __init__(self, redis: "Redis"):
        """초기화.

        Args:
            redis: Redis 클라이언트
        """
        self._redis = redis

    def _pending_key(self, job_id: str) -> str:
        """대기 요청 키 생성."""
        return f"{PENDING_REQUEST_PREFIX}:{job_id}"

    def _state_key(self, job_id: str) -> str:
        """상태 키 생성."""
        return f"{PIPELINE_STATE_PREFIX}:{job_id}"

    async def save_pending_request(
        self,
        job_id: str,
        request: HumanInputRequest,
    ) -> None:
        """대기 중인 입력 요청 저장."""
        key = self._pending_key(job_id)
        data = {
            "job_id": request.job_id,
            "input_type": request.input_type.value,
            "message": request.message,
            "timeout": request.timeout,
        }

        await self._redis.set(
            key,
            json.dumps(data, ensure_ascii=False),
            ex=STATE_TTL,
        )

        logger.debug(
            "Pending request saved",
            extra={"job_id": job_id, "input_type": request.input_type.value},
        )

    async def get_pending_request(
        self,
        job_id: str,
    ) -> HumanInputRequest | None:
        """대기 중인 입력 요청 조회."""
        key = self._pending_key(job_id)
        raw = await self._redis.get(key)

        if raw is None:
            return None

        data = json.loads(raw)

        return HumanInputRequest(
            job_id=data["job_id"],
            input_type=InputType.from_string(data["input_type"]),
            message=data["message"],
            timeout=data["timeout"],
        )

    async def mark_completed(
        self,
        job_id: str,
    ) -> None:
        """입력 완료 처리.

        대기 중인 요청을 삭제합니다.
        """
        key = self._pending_key(job_id)
        await self._redis.delete(key)

        logger.debug("Interaction completed", extra={"job_id": job_id})

    async def save_pipeline_state(
        self,
        job_id: str,
        state: dict[str, Any],
        resume_node: str,
    ) -> None:
        """파이프라인 상태 스냅샷 저장."""
        key = self._state_key(job_id)
        data = {
            "state": state,
            "resume_node": resume_node,
        }

        await self._redis.set(
            key,
            json.dumps(data, ensure_ascii=False, default=str),
            ex=STATE_TTL,
        )

        logger.debug(
            "Pipeline state saved",
            extra={"job_id": job_id, "resume_node": resume_node},
        )

    async def get_pipeline_state(
        self,
        job_id: str,
    ) -> tuple[dict[str, Any], str] | None:
        """파이프라인 상태 스냅샷 조회."""
        key = self._state_key(job_id)
        raw = await self._redis.get(key)

        if raw is None:
            return None

        data = json.loads(raw)
        return data["state"], data["resume_node"]

    async def clear_state(
        self,
        job_id: str,
    ) -> None:
        """모든 상태 삭제.

        파이프라인 완료 후 정리.
        """
        pending_key = self._pending_key(job_id)
        state_key = self._state_key(job_id)

        await self._redis.delete(pending_key, state_key)

        logger.debug("All state cleared", extra={"job_id": job_id})
