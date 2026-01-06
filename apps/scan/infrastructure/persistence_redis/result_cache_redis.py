"""Result Cache Redis Adapter - 결과 캐시 저장/조회.

domains 의존성 제거 - 내부 messaging 모듈 사용.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import redis

from scan.application.result.ports.result_cache import ResultCache
from scan.infrastructure.messaging import (
    get_async_cache_client,
    get_async_streams_client,
)

logger = logging.getLogger(__name__)

# 기본 TTL (1시간)
DEFAULT_RESULT_CACHE_TTL = 3600


class ResultCacheRedis(ResultCache):
    """결과 캐시 Redis Adapter.

    파이프라인 완료 결과를 Cache Redis에 저장하고 조회합니다.

    Key 패턴:
    - 결과: scan:result:{job_id}
    - 상태: scan:state:{job_id} (Event Router가 관리)
    """

    def __init__(
        self,
        redis_url: str | None = None,
        default_ttl: int = DEFAULT_RESULT_CACHE_TTL,
    ):
        """초기화.

        Args:
            redis_url: Redis URL (None이면 환경변수에서 가져옴)
            default_ttl: 기본 TTL (초)
        """
        self._redis_url = redis_url or os.getenv(
            "REDIS_CACHE_URL",
            "redis://rfr-cache-redis.redis.svc.cluster.local:6379/0",
        )
        self._default_ttl = default_ttl
        self._sync_client: redis.Redis | None = None

    async def get(self, job_id: str) -> dict[str, Any] | None:
        """결과 조회 (비동기)."""
        cache_key = f"scan:result:{job_id}"

        try:
            client = await get_async_cache_client()
            data = await client.get(cache_key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(
                "result_cache_get_failed",
                extra={"job_id": job_id, "error": str(e)},
            )

        return None

    def set_sync(
        self,
        job_id: str,
        result: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        """결과 저장 (동기 버전, Celery Worker용)."""
        cache_key = f"scan:result:{job_id}"
        ttl = ttl_seconds or self._default_ttl

        try:
            client = self._get_sync_client()
            client.setex(cache_key, ttl, json.dumps(result))
            logger.debug(
                "result_cache_set",
                extra={"job_id": job_id, "ttl": ttl},
            )
        except Exception as e:
            logger.warning(
                "result_cache_set_failed",
                extra={"job_id": job_id, "error": str(e)},
            )

    async def get_state(self, job_id: str) -> dict[str, Any] | None:
        """현재 작업 상태 조회 (State KV)."""
        state_key = f"scan:state:{job_id}"

        try:
            client = await get_async_streams_client()
            data = await client.get(state_key)
            if data:
                if isinstance(data, bytes):
                    data = data.decode()
                return json.loads(data)
        except Exception as e:
            logger.warning(
                "state_kv_get_failed",
                extra={"job_id": job_id, "error": str(e)},
            )

        return None

    def _get_sync_client(self) -> redis.Redis:
        """동기 Redis 클라이언트 반환."""
        if self._sync_client is None:
            self._sync_client = redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
            )
        return self._sync_client
