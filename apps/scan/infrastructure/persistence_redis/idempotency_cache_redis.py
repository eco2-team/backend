"""Idempotency Cache Redis Adapter - 멱등성 캐시 Redis 구현체.

domains 의존성 제거 - 내부 messaging 모듈 사용.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from scan.application.classify.ports.idempotency_cache import IdempotencyCache
from scan.infrastructure.messaging import get_async_cache_client

logger = logging.getLogger(__name__)


class IdempotencyCacheRedis(IdempotencyCache):
    """멱등성 캐시 Redis Adapter.

    동일한 요청의 중복 제출을 방지합니다.

    Key 패턴: scan:idempotency:{key}
    """

    async def get(self, key: str) -> dict[str, Any] | None:
        """캐시된 응답 조회."""
        cache_key = f"scan:idempotency:{key}"

        try:
            client = await get_async_cache_client()
            data = await client.get(cache_key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(
                "idempotency_cache_get_failed",
                extra={"key": key, "error": str(e)},
            )

        return None

    async def set(self, key: str, response: dict[str, Any], ttl: int) -> None:
        """응답 캐시 저장."""
        cache_key = f"scan:idempotency:{key}"

        try:
            client = await get_async_cache_client()
            await client.setex(cache_key, ttl, json.dumps(response))
            logger.debug(
                "idempotency_cache_set",
                extra={"key": key, "ttl": ttl},
            )
        except Exception as e:
            logger.warning(
                "idempotency_cache_set_failed",
                extra={"key": key, "error": str(e)},
            )
