"""Chat 도메인 예외."""

from chat.domain.exceptions.base import DomainError


class ChatNotFoundError(DomainError):
    """채팅을 찾을 수 없음."""

    def __init__(self, chat_id: str | None = None) -> None:
        super().__init__("Chat not found")


class ChatAccessDeniedError(DomainError):
    """채팅 접근 권한 없음."""

    def __init__(self) -> None:
        super().__init__("Access denied")
