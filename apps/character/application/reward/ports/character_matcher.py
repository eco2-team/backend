"""Character Matcher Port."""

from abc import ABC, abstractmethod

from apps.character.domain.entities import Character


class CharacterMatcher(ABC):
    """캐릭터 매칭 포트.

    분류 결과를 기반으로 캐릭터를 매칭합니다.
    """

    @abstractmethod
    async def match_by_label(self, match_label: str) -> Character | None:
        """매칭 라벨로 캐릭터를 찾습니다.

        Args:
            match_label: 매칭 라벨 (중분류)

        Returns:
            매칭된 캐릭터 또는 None
        """
        ...

    @abstractmethod
    async def get_default(self) -> Character:
        """기본 캐릭터를 반환합니다.

        매칭 실패 시 사용됩니다.

        Returns:
            기본 캐릭터
        """
        ...
