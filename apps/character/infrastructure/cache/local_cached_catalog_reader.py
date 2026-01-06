"""Local Cached Catalog Reader Implementation.

로컬 인메모리 캐시를 사용하는 CatalogReader 구현입니다.
Redis 의존성 없이 빠른 응답을 제공합니다.

Architecture:
    - 로컬 캐시가 초기화된 경우: 캐시에서 즉시 반환
    - 로컬 캐시가 비어있는 경우: delegate(DB Reader)로 fallback
"""

from __future__ import annotations

import logging
from typing import Sequence

from character.application.catalog.ports import CatalogReader
from character.domain.entities import Character
from character.infrastructure.cache.character_cache import (
    CharacterLocalCache,
    get_character_cache,
)

logger = logging.getLogger(__name__)


class LocalCachedCatalogReader(CatalogReader):
    """로컬 인메모리 캐시를 활용한 카탈로그 Reader.

    DB Reader를 데코레이트하여 로컬 캐시 레이어를 추가합니다.
    Redis 의존성이 없어 더 빠르고 안정적입니다.

    Flow:
        1. 로컬 캐시 확인 (initialized && count > 0)
        2. 캐시 hit → 즉시 반환
        3. 캐시 miss → delegate(DB Reader) 호출 → 캐시에 저장 → 반환
    """

    def __init__(
        self,
        delegate: CatalogReader,
        cache: CharacterLocalCache | None = None,
    ) -> None:
        """Initialize.

        Args:
            delegate: 실제 DB Reader
            cache: 로컬 캐시 (None이면 싱글톤 사용)
        """
        self._delegate = delegate
        self._cache = cache or get_character_cache()

    async def list_all(self) -> Sequence[Character]:
        """캐시된 캐릭터 목록을 조회합니다.

        Returns:
            캐릭터 목록 (캐시 또는 DB에서)
        """
        # 1. 로컬 캐시 확인
        if self._cache.is_initialized and self._cache.count() > 0:
            logger.debug("Cache hit for catalog (local)")
            cached_chars = self._cache.get_all()
            return [
                Character(
                    id=c.id,
                    code=c.code,
                    name=c.name,
                    description=c.description,
                    type_label=c.type_label,
                    dialog=c.dialog,
                    match_label=c.match_label,
                )
                for c in cached_chars
            ]

        # 2. 캐시 miss → DB 조회
        logger.debug("Cache miss for catalog, fetching from DB")
        characters = await self._delegate.list_all()

        # 3. 로컬 캐시에 저장 (비동기 이벤트 대신 직접 저장)
        if characters:
            self._cache.set_all(list(characters))

        return characters
