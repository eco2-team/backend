"""SQLAlchemy ORM mappings."""

from apps.users.infrastructure.persistence_postgres.mappings.user import (
    start_user_mapper,
    users_table,
)
from apps.users.infrastructure.persistence_postgres.mappings.user_character import (
    start_user_character_mapper,
    user_characters_table,
)


def start_mappers() -> None:
    """모든 ORM 매핑을 시작합니다."""
    start_user_mapper()
    start_user_character_mapper()


__all__ = [
    "start_mappers",
    "users_table",
    "user_characters_table",
]
