"""Character Domain Enums."""

from enum import Enum


class CharacterOwnershipStatus(str, Enum):
    """캐릭터 소유 상태."""

    OWNED = "owned"
    INACTIVE = "inactive"


class CharacterRewardSource(str, Enum):
    """캐릭터 리워드 소스."""

    SCAN = "scan"
    QUEST = "quest"
