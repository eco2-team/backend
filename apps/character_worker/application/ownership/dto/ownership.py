"""Ownership DTOs."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OwnershipEvent:
    """캐릭터 소유권 이벤트.

    Celery 태스크에서 전달받는 데이터입니다.

    Attributes:
        user_id: 사용자 ID
        character_id: 캐릭터 ID
        character_code: 캐릭터 코드
        source: 획득 소스
    """

    user_id: UUID
    character_id: UUID
    character_code: str
    source: str = "scan-reward"


@dataclass(frozen=True, slots=True)
class SaveOwnershipResult:
    """소유권 저장 결과.

    Attributes:
        success: 성공 여부
        inserted: 새로 삽입된 개수
        skipped: 중복으로 스킵된 개수
        failed: 실패한 개수
        should_retry: 재시도 필요 여부
    """

    success: bool
    inserted: int = 0
    skipped: int = 0
    failed: int = 0
    should_retry: bool = False
