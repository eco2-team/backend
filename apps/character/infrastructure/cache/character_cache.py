"""Thread-safe singleton character cache for event-driven local caching.

API 서버 시작 시 DB에서 캐릭터 목록을 로드하고,
MQ 이벤트(character.cache fanout exchange)를 통해 실시간으로 동기화합니다.

Architecture:
    - 싱글톤 패턴: 모든 요청에서 동일한 캐시 인스턴스 사용
    - Thread-safe: Lock을 사용한 동시성 제어
    - Event-driven: MQ broadcast로 다중 인스턴스 간 동기화
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from threading import Lock
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class CachedCharacter:
    """캐시에 저장되는 캐릭터 정보.

    도메인 엔티티(Character)와 호환되도록 동일한 필드를 포함합니다.
    """

    id: UUID
    code: str
    name: str
    type_label: str | None
    dialog: str | None
    description: str | None = None
    match_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """dict 변환."""
        return {
            "id": str(self.id),
            "code": self.code,
            "name": self.name,
            "type_label": self.type_label,
            "dialog": self.dialog,
            "description": self.description,
            "match_label": self.match_label,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CachedCharacter:
        """dict에서 생성."""
        char_id = data.get("id", "")
        if isinstance(char_id, str):
            char_id = UUID(char_id) if char_id else UUID(int=0)
        return cls(
            id=char_id,
            code=data.get("code", ""),
            name=data.get("name", ""),
            type_label=data.get("type_label"),
            dialog=data.get("dialog"),
            description=data.get("description"),
            match_label=data.get("match_label"),
        )

    @classmethod
    def from_entity(cls, entity: Any) -> CachedCharacter:
        """도메인 엔티티(Character)에서 생성."""
        return cls(
            id=entity.id,
            code=entity.code,
            name=entity.name,
            type_label=entity.type_label,
            dialog=entity.dialog,
            description=getattr(entity, "description", None),
            match_label=getattr(entity, "match_label", None),
        )


class CharacterLocalCache:
    """Thread-safe 싱글톤 캐릭터 캐시.

    모든 API 요청에서 공유되는 인메모리 캐시입니다.
    MQ 이벤트를 통해 실시간으로 동기화됩니다.

    Usage:
        cache = get_character_cache()
        characters = cache.get_all()
    """

    _instance: CharacterLocalCache | None = None
    _lock = Lock()

    def __new__(cls) -> CharacterLocalCache:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._characters: dict[str, CachedCharacter] = {}
                    instance._initialized = False
                    instance._data_lock = Lock()
                    cls._instance = instance
        return cls._instance

    @property
    def is_initialized(self) -> bool:
        """캐시가 초기화되었는지 여부."""
        return self._initialized

    def set_all(self, characters: list[dict[str, Any] | Any]) -> None:
        """전체 캐시 교체 (초기화 또는 full refresh).

        Args:
            characters: 캐릭터 목록 (dict 또는 도메인 엔티티)
        """
        with self._data_lock:
            self._characters.clear()
            for char in characters:
                if isinstance(char, dict):
                    cached = CachedCharacter.from_dict(char)
                else:
                    cached = CachedCharacter.from_entity(char)
                self._characters[str(cached.id)] = cached
            self._initialized = True
            logger.info(
                "character_cache_initialized",
                extra={"count": len(self._characters)},
            )

    def upsert(self, character: dict[str, Any] | Any) -> None:
        """단일 캐릭터 추가/수정.

        Args:
            character: 캐릭터 데이터 (dict 또는 도메인 엔티티)
        """
        with self._data_lock:
            if isinstance(character, dict):
                cached = CachedCharacter.from_dict(character)
            else:
                cached = CachedCharacter.from_entity(character)
            self._characters[str(cached.id)] = cached
            logger.debug(
                "character_cache_upserted",
                extra={"character_id": str(cached.id), "name": cached.name},
            )

    def delete(self, character_id: str | UUID) -> None:
        """단일 캐릭터 삭제.

        Args:
            character_id: 삭제할 캐릭터 ID
        """
        char_id = str(character_id)
        with self._data_lock:
            removed = self._characters.pop(char_id, None)
            if removed:
                logger.debug(
                    "character_cache_deleted",
                    extra={"character_id": char_id},
                )

    def get(self, character_id: str | UUID) -> CachedCharacter | None:
        """단일 캐릭터 조회.

        Args:
            character_id: 조회할 캐릭터 ID

        Returns:
            캐시된 캐릭터 또는 None
        """
        return self._characters.get(str(character_id))

    def get_all(self) -> list[CachedCharacter]:
        """전체 캐릭터 목록 조회.

        Returns:
            캐시된 모든 캐릭터 목록
        """
        with self._data_lock:
            return list(self._characters.values())

    def get_by_match_label(self, match_label: str) -> CachedCharacter | None:
        """매칭 라벨로 캐릭터 조회.

        Chat Worker의 gRPC 호출에서 사용됩니다.
        폐기물 중분류(예: "플라스틱")로 캐릭터를 찾습니다.

        Args:
            match_label: 폐기물 중분류

        Returns:
            매칭된 캐릭터 또는 None
        """
        with self._data_lock:
            for char in self._characters.values():
                if char.match_label == match_label:
                    return char
        return None

    def count(self) -> int:
        """캐시된 캐릭터 수."""
        return len(self._characters)

    def clear(self) -> None:
        """캐시 초기화 (테스트용)."""
        with self._data_lock:
            self._characters.clear()
            self._initialized = False
            logger.warning("character_cache_cleared")


def get_character_cache() -> CharacterLocalCache:
    """싱글톤 캐릭터 캐시 인스턴스 반환.

    Returns:
        CharacterLocalCache 싱글톤 인스턴스
    """
    return CharacterLocalCache()
