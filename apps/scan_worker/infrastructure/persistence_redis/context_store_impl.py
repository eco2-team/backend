"""Redis Context Store - ContextStorePort 구현체.

체크포인팅을 위한 Redis 기반 저장소.
Step 완료 시 Context를 저장하여 실패 복구 지원.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import redis

from scan_worker.application.classify.ports.context_store import ContextStorePort

logger = logging.getLogger(__name__)

# Step 순서 (체크포인트 비교용)
STEP_ORDER = {
    "vision": 1,
    "rule": 2,
    "answer": 3,
    "reward": 4,
}

# 기본 TTL: 1시간 (대부분 파이프라인은 수 분 내 완료)
DEFAULT_CHECKPOINT_TTL = 3600


class RedisContextStore(ContextStorePort):
    """Redis 기반 Context 저장소.

    체크포인팅으로 실패 복구 지원.
    멱등성 보장 (이미 완료된 Step은 건너뜀).
    """

    def __init__(
        self,
        redis_url: str | None = None,
        ttl: int = DEFAULT_CHECKPOINT_TTL,
        key_prefix: str = "scan:checkpoint",
    ):
        """초기화.

        Args:
            redis_url: Redis URL (None이면 환경변수 사용)
            ttl: 체크포인트 TTL (초)
            key_prefix: Redis 키 prefix
        """
        self._redis_url = redis_url or os.environ.get(
            "REDIS_CACHE_URL",
            "redis://rfr-cache-redis.redis.svc.cluster.local:6379/0",
        )
        self._ttl = ttl
        self._key_prefix = key_prefix
        self._client: redis.Redis | None = None
        logger.info(
            "RedisContextStore initialized (ttl=%d)",
            ttl,
        )

    def _get_client(self) -> redis.Redis:
        """Lazy Redis 클라이언트 생성."""
        if self._client is None:
            self._client = redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
            )
        return self._client

    def _get_key(self, task_id: str, step_name: str) -> str:
        """Redis 키 생성."""
        return f"{self._key_prefix}:{task_id}:{step_name}"

    def _get_pattern(self, task_id: str) -> str:
        """작업의 모든 체크포인트 패턴."""
        return f"{self._key_prefix}:{task_id}:*"

    def save_checkpoint(
        self,
        task_id: str,
        step_name: str,
        context: dict[str, Any],
    ) -> None:
        """Step 완료 후 Context 저장."""
        client = self._get_client()
        key = self._get_key(task_id, step_name)

        try:
            client.setex(
                key,
                self._ttl,
                json.dumps(context, ensure_ascii=False),
            )
            logger.debug(
                "checkpoint_saved",
                extra={
                    "task_id": task_id,
                    "step": step_name,
                    "ttl": self._ttl,
                },
            )
        except Exception as e:
            logger.warning(
                "checkpoint_save_failed",
                extra={
                    "task_id": task_id,
                    "step": step_name,
                    "error": str(e),
                },
            )
            # 체크포인트 저장 실패는 치명적이지 않음 (파이프라인은 계속 진행)

    def get_checkpoint(
        self,
        task_id: str,
        step_name: str,
    ) -> dict[str, Any] | None:
        """저장된 체크포인트 조회."""
        client = self._get_client()
        key = self._get_key(task_id, step_name)

        try:
            data = client.get(key)
            if data:
                logger.debug(
                    "checkpoint_found",
                    extra={"task_id": task_id, "step": step_name},
                )
                return json.loads(data)
        except Exception as e:
            logger.warning(
                "checkpoint_get_failed",
                extra={
                    "task_id": task_id,
                    "step": step_name,
                    "error": str(e),
                },
            )
        return None

    def get_latest_checkpoint(
        self,
        task_id: str,
    ) -> tuple[str, dict[str, Any]] | None:
        """가장 최근 체크포인트 조회."""
        client = self._get_client()
        pattern = self._get_pattern(task_id)

        try:
            keys = list(client.scan_iter(match=pattern, count=100))
            if not keys:
                return None

            # Step 순서로 정렬하여 가장 마지막 것 찾기
            latest_step = None
            latest_order = -1
            latest_ctx = None

            for key in keys:
                # scan:checkpoint:{task_id}:{step_name}
                step_name = key.split(":")[-1]
                order = STEP_ORDER.get(step_name, 0)

                if order > latest_order:
                    data = client.get(key)
                    if data:
                        latest_step = step_name
                        latest_order = order
                        latest_ctx = json.loads(data)

            if latest_step and latest_ctx:
                logger.info(
                    "latest_checkpoint_found",
                    extra={"task_id": task_id, "step": latest_step},
                )
                return (latest_step, latest_ctx)

        except Exception as e:
            logger.warning(
                "latest_checkpoint_get_failed",
                extra={"task_id": task_id, "error": str(e)},
            )
        return None

    def clear_checkpoints(self, task_id: str) -> None:
        """작업의 모든 체크포인트 삭제."""
        client = self._get_client()
        pattern = self._get_pattern(task_id)

        try:
            keys = list(client.scan_iter(match=pattern, count=100))
            if keys:
                client.delete(*keys)
                logger.debug(
                    "checkpoints_cleared",
                    extra={"task_id": task_id, "count": len(keys)},
                )
        except Exception as e:
            logger.warning(
                "checkpoints_clear_failed",
                extra={"task_id": task_id, "error": str(e)},
            )
