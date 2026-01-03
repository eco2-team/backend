"""PostgreSQL Persistence."""

from apps.character_worker.infrastructure.persistence_postgres.ownership_store_sqla import (
    SqlaOwnershipStore,
)

__all__ = ["SqlaOwnershipStore"]
