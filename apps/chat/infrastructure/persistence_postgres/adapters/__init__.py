"""Chat Persistence Adapters."""

from chat.infrastructure.persistence_postgres.adapters.chat_repository_sqla import (
    ChatRepositorySQLA,
)

__all__ = ["ChatRepositorySQLA"]
