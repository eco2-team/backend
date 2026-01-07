"""Character Worker Domain Enums.

character 서비스에서 필요한 enum만 복사.
마이크로서비스 독립성을 위해 중복 허용.
"""

from enum import Enum


class CharacterOwnershipStatus(str, Enum):
    """캐릭터 소유 상태."""

    OWNED = "owned"
    INACTIVE = "inactive"


class CharacterRewardSource(str, Enum):
    """캐릭터 리워드 소스."""

    SCAN = "scan"
    QUEST = "quest"
