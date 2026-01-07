"""Character Worker Domain Layer.

도메인 엔티티 및 DTO를 정의합니다.
마이크로서비스 독립성을 위해 자체 도메인 모델 보유.
"""

from character_worker.domain.entities import Character, CharacterOwnership
from character_worker.domain.enums import CharacterOwnershipStatus, CharacterRewardSource

__all__ = [
    "Character",
    "CharacterOwnership",
    "CharacterOwnershipStatus",
    "CharacterRewardSource",
]
