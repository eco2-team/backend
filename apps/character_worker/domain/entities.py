"""Character Worker Domain Entities.

character 서비스에서 필요한 엔티티만 복사.
마이크로서비스 독립성을 위해 중복 허용.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from character_worker.domain.enums import CharacterOwnershipStatus


@dataclass
class Character:
    """캐릭터 엔티티.

    수집 가능한 캐릭터의 정적 정의입니다.

    Attributes:
        id: 캐릭터 고유 ID
        code: 캐릭터 코드 (unique)
        name: 캐릭터 이름
        description: 캐릭터 설명
        type_label: 캐릭터 타입 라벨
        dialog: 캐릭터 대사
        match_label: 매칭 라벨 (분류 결과와 매칭에 사용)
        created_at: 생성 시각
        updated_at: 수정 시각
    """

    id: UUID
    code: str
    name: str
    type_label: str
    dialog: str
    description: str | None = None
    match_label: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Character):
            return False
        return self.id == other.id


@dataclass
class CharacterOwnership:
    """캐릭터 소유권 엔티티.

    사용자가 보유한 캐릭터 정보입니다.

    Attributes:
        id: 소유권 레코드 ID
        user_id: 사용자 ID
        character_id: 캐릭터 ID
        character_code: 캐릭터 코드 (멱등성 키)
        source: 획득 소스 (예: "scan-reward")
        status: 소유 상태
        acquired_at: 획득 시각
        updated_at: 수정 시각
        character: 연관된 캐릭터 엔티티 (옵션)
    """

    id: UUID
    user_id: UUID
    character_id: UUID
    character_code: str
    status: CharacterOwnershipStatus
    source: str | None = None
    acquired_at: datetime | None = None
    updated_at: datetime | None = None
    character: Character | None = None

    def __hash__(self) -> int:
        return hash(self.id)
