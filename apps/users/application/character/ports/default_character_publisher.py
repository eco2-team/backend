"""Default Character Publisher Port.

기본 캐릭터 지급 이벤트를 발행하는 포트입니다.
character_worker가 이벤트를 수신하여 기본 캐릭터 정보를 조회하고 저장합니다.
"""

from abc import ABC, abstractmethod
from uuid import UUID


class DefaultCharacterPublisher(ABC):
    """기본 캐릭터 지급 이벤트 발행 포트.

    users 도메인은 캐릭터 정보를 모릅니다.
    user_id만 전달하면 character_worker가 기본 캐릭터 정보를 조회하여 저장합니다.

    Flow:
        1. users API: 빈 리스트 감지 → publish(user_id)
        2. character_worker: 이벤트 수신 → 기본 캐릭터 정보 조회 → users.user_characters 저장
    """

    @abstractmethod
    def publish(self, user_id: UUID) -> None:
        """기본 캐릭터 지급 이벤트를 발행합니다.

        Fire-and-forget 방식으로 비동기 처리됩니다.
        character_worker가 기본 캐릭터 정보를 조회하여 저장합니다.

        Args:
            user_id: 사용자 ID
        """
        ...
