"""Character Entity.

캐릭터 정의 엔티티입니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


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
