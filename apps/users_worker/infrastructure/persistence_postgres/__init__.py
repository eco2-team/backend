"""PostgreSQL Persistence."""

from apps.users_worker.infrastructure.persistence_postgres.character_store_sqla import (
    SqlaCharacterStore,
)

__all__ = ["SqlaCharacterStore"]
