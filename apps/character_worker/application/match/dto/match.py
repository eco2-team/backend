"""Match DTOs."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class MatchRequest:
    """캐릭터 매칭 요청.

    Attributes:
        task_id: 태스크 ID
        user_id: 사용자 ID
        middle_category: 중분류 (매칭 라벨)
    """

    task_id: str
    user_id: UUID
    middle_category: str


@dataclass(frozen=True, slots=True)
class MatchResult:
    """캐릭터 매칭 결과.

    Attributes:
        success: 매칭 성공 여부
        character_id: 매칭된 캐릭터 ID
        character_code: 캐릭터 코드
        character_name: 캐릭터 이름
        character_type: 캐릭터 타입
        dialog: 캐릭터 대사
        is_default: 기본 캐릭터 여부
    """

    success: bool
    character_id: UUID | None = None
    character_code: str | None = None
    character_name: str | None = None
    character_type: str | None = None
    dialog: str | None = None
    is_default: bool = False
