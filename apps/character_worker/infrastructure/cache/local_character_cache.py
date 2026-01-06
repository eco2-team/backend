"""Local Character Cache Implementation."""

import logging
from typing import Mapping

from apps.character.domain.entities import Character
from character_worker.application.match.ports import CharacterCache

logger = logging.getLogger(__name__)


class LocalCharacterCache(CharacterCache):
    """로컬 메모리 캐릭터 캐시.

    Worker 프로세스 시작 시 DB에서 로드됩니다.
    HPA 스케일아웃 시 각 Pod마다 초기화됩니다.
    """

    def __init__(self) -> None:
        """Initialize."""
        self._cache: dict[str, Character] = {}
        self._default: Character | None = None
        self._loaded: bool = False

    def get_by_match_label(self, label: str) -> Character | None:
        """매칭 라벨로 캐릭터를 조회합니다."""
        return self._cache.get(label)

    def get_default(self) -> Character | None:
        """기본 캐릭터를 반환합니다."""
        return self._default

    def load(self, characters: Mapping[str, Character], default_code: str) -> None:
        """캐릭터 데이터를 로드합니다."""
        self._cache = dict(characters)

        # 기본 캐릭터 찾기
        for char in characters.values():
            if char.code == default_code:
                self._default = char
                break

        self._loaded = True
        logger.info(
            "Character cache loaded",
            extra={
                "count": len(self._cache),
                "default_code": default_code,
                "has_default": self._default is not None,
            },
        )

    def is_loaded(self) -> bool:
        """캐시가 로드되었는지 확인합니다."""
        return self._loaded


# 싱글톤 인스턴스
_cache_instance: LocalCharacterCache | None = None


def get_character_cache() -> LocalCharacterCache:
    """캐릭터 캐시 싱글톤을 반환합니다."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = LocalCharacterCache()
    return _cache_instance
