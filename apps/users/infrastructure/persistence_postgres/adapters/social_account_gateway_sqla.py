"""SQLAlchemy implementation of social account gateway.

Note: auth.user_social_accounts 테이블을 읽기 전용으로 조회합니다.
이 테이블은 auth 도메인이 소유하지만, users 도메인에서 프로필 조회 시 필요합니다.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Column, DateTime, MetaData, String, Table, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession

from apps.users.application.identity.ports.social_account_gateway import SocialAccountInfo
from apps.users.infrastructure.persistence_postgres.constants import (
    AUTH_SCHEMA,
    AUTH_USER_SOCIAL_ACCOUNTS_TABLE,
)

# auth 스키마 (읽기 전용)
auth_metadata = MetaData(schema=AUTH_SCHEMA)

# auth.user_social_accounts 테이블 정의 (읽기 전용)
auth_social_accounts_table = Table(
    AUTH_USER_SOCIAL_ACCOUNTS_TABLE,
    auth_metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("user_id", PGUUID(as_uuid=True), nullable=False),
    Column("provider", String(32), nullable=False),
    Column("provider_user_id", String(255), nullable=False),
    Column("email", String(320), nullable=True),
    Column("last_login_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


class SqlaSocialAccountQueryGateway:
    """소셜 계정 조회 게이트웨이 SQLAlchemy 구현.

    auth 스키마의 테이블을 읽기 전용으로 조회합니다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user_id(self, user_id: UUID) -> list[SocialAccountInfo]:
        """사용자의 소셜 계정 목록을 조회합니다."""
        result = await self._session.execute(
            select(auth_social_accounts_table).where(
                auth_social_accounts_table.c.user_id == user_id
            )
        )
        rows = result.fetchall()
        return [
            SocialAccountInfo(
                provider=row.provider,
                provider_user_id=row.provider_user_id,
                email=row.email,
                last_login_at=row.last_login_at,
            )
            for row in rows
        ]

    async def get_by_provider(self, user_id: UUID, provider: str) -> SocialAccountInfo | None:
        """특정 프로바이더의 소셜 계정을 조회합니다."""
        result = await self._session.execute(
            select(auth_social_accounts_table).where(
                auth_social_accounts_table.c.user_id == user_id,
                auth_social_accounts_table.c.provider == provider,
            )
        )
        row = result.fetchone()
        if row is None:
            return None
        return SocialAccountInfo(
            provider=row.provider,
            provider_user_id=row.provider_user_id,
            email=row.email,
            last_login_at=row.last_login_at,
        )
