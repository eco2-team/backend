"""Users ORM Mapping.

User 도메인 엔티티와 DB 테이블의 매핑입니다.

타입 규칙 (Unbounded String 기본 전략):
    - TEXT: 기본 문자열 타입 (PostgreSQL에서 VARCHAR와 성능 동일)
    - VARCHAR: 표준 규격이 명확한 경우만 사용
        - phone_number: VARCHAR(20) - E.164 표준
"""

from sqlalchemy import Table, Column, String, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from apps.auth.infrastructure.persistence_postgres.registry import mapper_registry


users_table = Table(
    "users",
    mapper_registry.metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("username", Text),
    Column("nickname", Text),
    Column("profile_image_url", Text),
    Column("phone_number", String(20), index=True),  # E.164
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("last_login_at", DateTime(timezone=True)),
    UniqueConstraint("username", "phone_number", name="uq_auth_users_name_phone"),
    schema="auth",
)


def start_users_mapper() -> None:
    """Users 매퍼 시작.

    Note:
        Imperative Mapping 사용.
        도메인 엔티티가 SQLAlchemy에 의존하지 않도록 합니다.
    """
    from apps.auth.domain.entities.user import User

    # 이미 매핑된 경우 스킵
    if hasattr(User, "__mapper__"):
        return

    mapper_registry.map_imperatively(
        User,
        users_table,
        properties={
            # id_는 UserId Value Object로 변환
            # SQLAlchemy는 UUID를 직접 다루고, 변환은 Adapter에서 처리
        },
        column_prefix="_",
    )
