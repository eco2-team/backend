"""Thread-safe singleton character cache for event-driven local caching.

Worker 시작 시 DB에서 캐릭터 목록을 로드하고,
MQ 이벤트를 통해 실시간으로 동기화합니다.
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

    ScanRewardEvaluator와 호환되도록 match_label 속성을 포함합니다.
    """

    id: str
    code: str
    name: str
    type_label: str | None
    dialog: str | None
    # evaluator 매칭에 사용되는 필드
    match_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """dict 변환 (evaluator 호환)."""
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "type_label": self.type_label,
            "dialog": self.dialog,
            "match_label": self.match_label,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CachedCharacter:
        """dict에서 생성."""
        return cls(
            id=str(data.get("id", "")),
            code=data.get("code", ""),
            name=data.get("name", ""),
            type_label=data.get("type_label"),
            dialog=data.get("dialog"),
            match_label=data.get("match_label"),
        )

    @classmethod
    def from_model(cls, model: Any) -> CachedCharacter:
        """SQLAlchemy 모델에서 생성."""
        return cls(
            id=str(model.id),
            code=model.code,
            name=model.name,
            type_label=model.type_label,
            dialog=model.dialog,
            match_label=getattr(model, "match_label", None),
        )


class CharacterLocalCache:
    """Thread-safe 싱글톤 캐릭터 캐시.

    모든 Worker 프로세스에서 공유되는 인메모리 캐시입니다.
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
            characters: 캐릭터 목록 (dict 또는 SQLAlchemy 모델)
        """
        with self._data_lock:
            self._characters.clear()
            for char in characters:
                if isinstance(char, dict):
                    cached = CachedCharacter.from_dict(char)
                else:
                    cached = CachedCharacter.from_model(char)
                self._characters[cached.id] = cached
            self._initialized = True
            logger.info(
                "character_cache_initialized",
                extra={"count": len(self._characters)},
            )

    def upsert(self, character: dict[str, Any] | Any) -> None:
        """단일 캐릭터 추가/수정.

        Args:
            character: 캐릭터 데이터 (dict 또는 SQLAlchemy 모델)
        """
        with self._data_lock:
            if isinstance(character, dict):
                cached = CachedCharacter.from_dict(character)
            else:
                cached = CachedCharacter.from_model(character)
            self._characters[cached.id] = cached
            logger.info(
                "character_cache_upserted",
                extra={"character_id": cached.id, "name": cached.name},
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
                logger.info(
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

    def get_all_as_dicts(self) -> list[dict[str, Any]]:
        """전체 캐릭터 목록을 dict로 조회 (evaluator 호환).

        Returns:
            캐시된 모든 캐릭터 목록 (dict 형태)
        """
        with self._data_lock:
            return [char.to_dict() for char in self._characters.values()]

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
