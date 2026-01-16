"""Chat ORM Mappings.

Imperative mapping으로 Domain Entity와 DB Table을 연결합니다.
"""

from chat.infrastructure.persistence_postgres.mappings.chat import start_chat_mapper
from chat.infrastructure.persistence_postgres.mappings.message import start_message_mapper


def start_mappers() -> None:
    """모든 Chat 도메인 매퍼를 시작합니다."""
    start_chat_mapper()
    start_message_mapper()


__all__ = [
    "start_chat_mapper",
    "start_message_mapper",
    "start_mappers",
]
