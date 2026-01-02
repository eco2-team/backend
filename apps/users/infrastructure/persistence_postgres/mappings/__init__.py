"""SQLAlchemy ORM mappings."""

from apps.users.infrastructure.persistence_postgres.mappings.user import (
    accounts_table,
    start_user_mapper,
)
from apps.users.infrastructure.persistence_postgres.mappings.user_character import (
    start_user_character_mapper,
    user_characters_table,
)
from apps.users.infrastructure.persistence_postgres.mappings.user_social_account import (
    social_accounts_table,
    start_user_social_account_mapper,
)


def start_mappers() -> None:
    """모든 ORM 매핑을 시작합니다."""
    start_user_mapper()
    start_user_character_mapper()
    start_user_social_account_mapper()


__all__ = [
    "start_mappers",
    "accounts_table",
    "social_accounts_table",
    "user_characters_table",
]
