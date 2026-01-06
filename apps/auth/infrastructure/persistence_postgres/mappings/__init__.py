"""ORM Mappings.

도메인 엔티티와 DB 테이블의 매핑을 정의합니다.
"""

from apps.auth.infrastructure.persistence_postgres.mappings.login_audit import (
    login_audits_table,
    start_login_audit_mapper,
)
from apps.auth.infrastructure.persistence_postgres.mappings.users import (
    start_users_mapper,
    users_table,
)
from apps.auth.infrastructure.persistence_postgres.mappings.users_social_account import (
    start_users_social_account_mapper,
    users_social_accounts_table,
)


def start_all_mappers() -> None:
    """모든 매퍼 시작."""
    start_users_mapper()
    start_users_social_account_mapper()
    start_login_audit_mapper()


__all__ = [
    "users_table",
    "users_social_accounts_table",
    "login_audits_table",
    "start_users_mapper",
    "start_users_social_account_mapper",
    "start_login_audit_mapper",
    "start_all_mappers",
]
