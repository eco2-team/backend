"""Character Cache Port."""

from abc import ABC, abstractmethod
from typing import Mapping

from apps.character.domain.entities import Character


class CharacterCache(ABC):
    """캐릭터 로컬 캐시 포트.

    Worker 프로세스 내 메모리 캐시를 제공합니다.
    HPA 스케일아웃 시 각 Pod마다 초기화됩니다.
    """

    @abstractmethod
    def get_by_match_label(self, label: str) -> Character | None:
        """매칭 라벨로 캐릭터를 조회합니다.

        Args:
            label: 매칭 라벨 (중분류)

        Returns:
            캐릭터 또는 None
        """
        ...

    @abstractmethod
    def get_default(self) -> Character | None:
        """기본 캐릭터를 반환합니다.

        Returns:
            기본 캐릭터 또는 None
        """
        ...

    @abstractmethod
    def load(self, characters: Mapping[str, Character], default_code: str) -> None:
        """캐릭터 데이터를 로드합니다.

        Args:
            characters: 매칭 라벨 -> 캐릭터 매핑
            default_code: 기본 캐릭터 코드
        """
        ...

    @abstractmethod
    def is_loaded(self) -> bool:
        """캐시가 로드되었는지 확인합니다.

        Returns:
            로드 여부
        """
        ...
