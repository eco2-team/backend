"""Cached Catalog Reader Implementation."""

import json
import logging
from typing import Any, Sequence

from redis.asyncio import Redis

from character.application.catalog.ports import CatalogReader
from character.domain.entities import Character

logger = logging.getLogger(__name__)

CACHE_KEY = "character:catalog"
CACHE_TTL = 3600  # 1시간


class CachedCatalogReader(CatalogReader):
    """Redis 캐시를 활용한 카탈로그 Reader.

    DB Reader를 데코레이트하여 캐시 레이어를 추가합니다.
    """

    def __init__(self, delegate: CatalogReader, redis: Redis) -> None:
        """Initialize.

        Args:
            delegate: 실제 DB Reader
            redis: Redis 클라이언트
        """
        self._delegate = delegate
        self._redis = redis

    async def list_all(self) -> Sequence[Character]:
        """캐시된 캐릭터 목록을 조회합니다."""
        # 캐시 확인
        cached = await self._redis.get(CACHE_KEY)
        if cached:
            logger.debug("Cache hit for catalog")
            return self._deserialize(cached)

        # DB 조회
        logger.debug("Cache miss for catalog, fetching from DB")
        characters = await self._delegate.list_all()

        # 캐시 저장
        await self._redis.setex(
            CACHE_KEY,
            CACHE_TTL,
            self._serialize(characters),
        )

        return characters

    def _serialize(self, characters: Sequence[Character]) -> str:
        """캐릭터 목록을 JSON으로 직렬화합니다."""
        data = [
            {
                "id": str(c.id),
                "code": c.code,
                "name": c.name,
                "description": c.description,
                "type_label": c.type_label,
                "dialog": c.dialog,
                "match_label": c.match_label,
            }
            for c in characters
        ]
        return json.dumps(data)

    def _deserialize(self, data: str | bytes) -> Sequence[Character]:
        """JSON을 캐릭터 목록으로 역직렬화합니다."""
        from uuid import UUID

        if isinstance(data, bytes):
            data = data.decode("utf-8")

        items: list[dict[str, Any]] = json.loads(data)
        return [
            Character(
                id=UUID(item["id"]),
                code=item["code"],
                name=item["name"],
                description=item.get("description"),
                type_label=item["type_label"],
                dialog=item["dialog"],
                match_label=item.get("match_label"),
            )
            for item in items
        ]
