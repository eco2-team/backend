"""Message Entity - 메시지 도메인 엔티티.

각 채팅 세션 내의 개별 메시지.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass
class Message:
    """메시지 엔티티.

    Attributes:
        id: 메시지 ID (UUID)
        chat_id: 채팅 세션 ID (FK)
        role: 메시지 역할 ('user' | 'assistant')
        content: 메시지 내용
        intent: AI 분류 intent (assistant만)
        metadata: 추가 메타데이터 (node_results, citations 등)
        job_id: 비동기 작업 ID (응답 추적용)
        created_at: 생성 시간
    """

    chat_id: UUID
    role: str
    content: str
    id: UUID = field(default_factory=uuid4)
    intent: str | None = None
    metadata: dict[str, Any] | None = None
    job_id: UUID | None = None
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        """role 값 검증."""
        if self.role not in ("user", "assistant"):
            raise ValueError(f"Invalid role: {self.role}. Must be 'user' or 'assistant'.")

    @classmethod
    def user_message(
        cls,
        chat_id: UUID,
        content: str,
        job_id: UUID | None = None,
    ) -> "Message":
        """사용자 메시지 생성."""
        return cls(
            chat_id=chat_id,
            role="user",
            content=content,
            job_id=job_id,
        )

    @classmethod
    def assistant_message(
        cls,
        chat_id: UUID,
        content: str,
        intent: str | None = None,
        metadata: dict[str, Any] | None = None,
        job_id: UUID | None = None,
    ) -> "Message":
        """AI 응답 메시지 생성."""
        return cls(
            chat_id=chat_id,
            role="assistant",
            content=content,
            intent=intent,
            metadata=metadata,
            job_id=job_id,
        )
