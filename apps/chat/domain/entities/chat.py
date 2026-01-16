"""Chat Entity - 채팅 세션 도메인 엔티티.

사이드바에 표시되는 대화 목록의 각 항목.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4


@dataclass
class Chat:
    """채팅 세션 엔티티.

    Attributes:
        id: 채팅 ID (UUID)
        user_id: 사용자 ID (FK)
        title: 채팅 제목 (자동 생성 또는 NULL)
        preview: 마지막 메시지 미리보기
        message_count: 메시지 수
        last_message_at: 마지막 메시지 시간
        is_deleted: 삭제 여부 (soft delete)
        created_at: 생성 시간
        updated_at: 수정 시간
    """

    user_id: UUID
    id: UUID = field(default_factory=uuid4)
    title: str | None = None
    preview: str | None = None
    message_count: int = 0
    last_message_at: datetime | None = None
    is_deleted: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def update_on_new_message(self, preview: str) -> None:
        """새 메시지 추가 시 메타데이터 업데이트."""
        self.message_count += 1
        self.preview = preview[:100] if len(preview) > 100 else preview
        self.last_message_at = datetime.now()
        self.updated_at = datetime.now()

    def soft_delete(self) -> None:
        """Soft delete 처리."""
        self.is_deleted = True
        self.updated_at = datetime.now()
