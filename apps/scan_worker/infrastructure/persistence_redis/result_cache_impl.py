"""Redis Result Cache - ResultCachePort 구현체.

파이프라인 완료 결과 캐싱.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import redis

from scan_worker.application.classify.ports.result_cache import ResultCachePort

logger = logging.getLogger(__name__)

# 기본 TTL (1시간)
DEFAULT_RESULT_CACHE_TTL = 3600


class RedisResultCache(ResultCachePort):
    """Redis 기반 결과 캐시 구현체."""

    def __init__(
        self,
        redis_url: str | None = None,
        default_ttl: int | None = None,
    ):
        """초기화.

        Args:
            redis_url: Redis URL (None이면 환경변수 사용)
            default_ttl: 기본 TTL (초)
        """
        self._redis_url = redis_url or os.environ.get(
            "REDIS_CACHE_URL",
            "redis://rfr-cache-redis.redis.svc.cluster.local:6379/0",
        )
        self._default_ttl = default_ttl or int(
            os.environ.get("SCAN_RESULT_CACHE_TTL", str(DEFAULT_RESULT_CACHE_TTL))
        )
        self._client: redis.Redis | None = None
        logger.info(
            "RedisResultCache initialized (url=%s, ttl=%d)",
            self._redis_url,
            self._default_ttl,
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

    def cache_result(
        self,
        task_id: str,
        result: dict[str, Any],
        ttl: int | None = None,
    ) -> None:
        """결과를 캐시에 저장.

        Args:
            task_id: 작업 ID (UUID)
            result: 캐싱할 결과 데이터
            ttl: TTL (초), None이면 기본값 사용
        """
        cache_key = f"scan:result:{task_id}"
        effective_ttl = ttl or self._default_ttl

        try:
            client = self._get_client()
            client.setex(cache_key, effective_ttl, json.dumps(result))
            logger.debug(
                "scan_result_cached",
                extra={"task_id": task_id, "ttl": effective_ttl},
            )
        except Exception as e:
            logger.warning(
                "scan_result_cache_failed",
                extra={"task_id": task_id, "error": str(e)},
            )

    def get_result(self, task_id: str) -> dict[str, Any] | None:
        """캐시에서 결과 조회.

        Args:
            task_id: 작업 ID (UUID)

        Returns:
            캐싱된 결과 (없으면 None)
        """
        cache_key = f"scan:result:{task_id}"

        try:
            client = self._get_client()
            data = client.get(cache_key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning(
                "scan_result_get_failed",
                extra={"task_id": task_id, "error": str(e)},
            )
            return None
