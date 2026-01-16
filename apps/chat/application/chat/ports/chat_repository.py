"""Chat Repository Port - 채팅 저장소 추상화.

Clean Architecture의 Port로서 Application Layer에서 정의.
Infrastructure Layer에서 구현.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from chat.domain.entities.chat import Chat
    from chat.domain.entities.message import Message


class ChatRepositoryPort(ABC):
    """채팅 저장소 Port.

    채팅 세션 및 메시지 CRUD 작업을 추상화합니다.
    """

    # ─────────────────────────────────────────────────────────────
    # Chat (세션) 관련
    # ─────────────────────────────────────────────────────────────

    @abstractmethod
    async def get_chats_by_user(
        self,
        user_id: UUID,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list["Chat"], str | None]:
        """사용자의 채팅 목록 조회 (사이드바용).

        Args:
            user_id: 사용자 ID
            limit: 조회 개수
            cursor: 페이징 커서

        Returns:
            (채팅 목록, 다음 커서)
        """
        ...

    @abstractmethod
    async def get_chat_by_id(self, chat_id: UUID) -> "Chat | None":
        """채팅 상세 조회.

        Args:
            chat_id: 채팅 ID

        Returns:
            Chat 엔티티 또는 None
        """
        ...

    @abstractmethod
    async def create_chat(self, chat: "Chat") -> "Chat":
        """새 채팅 생성.

        Args:
            chat: Chat 엔티티

        Returns:
            생성된 Chat
        """
        ...

    @abstractmethod
    async def update_chat(self, chat: "Chat") -> "Chat":
        """채팅 업데이트.

        Args:
            chat: Chat 엔티티

        Returns:
            업데이트된 Chat
        """
        ...

    @abstractmethod
    async def delete_chat(self, chat_id: UUID) -> bool:
        """채팅 삭제 (soft delete).

        Args:
            chat_id: 채팅 ID

        Returns:
            삭제 성공 여부
        """
        ...

    # ─────────────────────────────────────────────────────────────
    # Message 관련
    # ─────────────────────────────────────────────────────────────

    @abstractmethod
    async def get_messages_by_chat(
        self,
        chat_id: UUID,
        limit: int = 50,
        before: str | None = None,
    ) -> tuple[list["Message"], bool]:
        """채팅의 메시지 목록 조회.

        Args:
            chat_id: 채팅 ID
            limit: 조회 개수
            before: 이 시간 이전 메시지만 조회 (페이징)

        Returns:
            (메시지 목록, 더 있는지 여부)
        """
        ...

    @abstractmethod
    async def create_message(self, message: "Message") -> "Message":
        """새 메시지 생성.

        Args:
            message: Message 엔티티

        Returns:
            생성된 Message
        """
        ...

    @abstractmethod
    async def get_message_by_job_id(self, job_id: UUID) -> "Message | None":
        """job_id로 메시지 조회 (응답 업데이트용).

        Args:
            job_id: Worker job_id

        Returns:
            Message 엔티티 또는 None
        """
        ...

    @abstractmethod
    async def update_message(self, message: "Message") -> "Message":
        """메시지 업데이트 (AI 응답 저장용).

        Args:
            message: Message 엔티티

        Returns:
            업데이트된 Message
        """
        ...

    # ─────────────────────────────────────────────────────────────
    # Batch 관련 (Eventual Consistency Consumer용)
    # ─────────────────────────────────────────────────────────────

    @abstractmethod
    async def bulk_create_messages(self, messages: list["Message"]) -> int:
        """메시지 일괄 생성 (배치 Consumer용).

        Args:
            messages: Message 엔티티 목록

        Returns:
            생성된 메시지 수
        """
        ...

    @abstractmethod
    async def update_conversation_metadata(
        self,
        chat_id: "UUID",
        message_count_delta: int,
        preview: str,
        last_message_at: "datetime",
    ) -> bool:
        """Conversation 메타데이터 업데이트.

        Args:
            chat_id: 채팅 ID
            message_count_delta: 메시지 수 증분
            preview: 미리보기 텍스트
            last_message_at: 마지막 메시지 시간

        Returns:
            업데이트 성공 여부
        """
        ...


__all__ = ["ChatRepositoryPort"]
