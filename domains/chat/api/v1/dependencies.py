from functools import lru_cache

from domains.chat.services.chat import ChatService


@lru_cache
def get_chat_service() -> ChatService:
    return ChatService()
