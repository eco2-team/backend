"""Character Store Port.

캐릭터 저장소 인터페이스를 정의합니다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from apps.users_worker.application.character.dto.event import CharacterEvent


class CharacterStore(Protocol):
    """캐릭터 저장소 인터페이스.

    Infrastructure 계층에서 구현합니다.
    """

    async def bulk_upsert(self, events: list["CharacterEvent"]) -> int:
        """캐릭터 배치 UPSERT.

        (user_id, character_code) 기준으로 중복 시 업데이트합니다.

        Args:
            events: 저장할 캐릭터 이벤트 목록

        Returns:
            처리된 레코드 수

        Raises:
            ConnectionError: DB 연결 실패
            TimeoutError: DB 타임아웃
        """
        ...
