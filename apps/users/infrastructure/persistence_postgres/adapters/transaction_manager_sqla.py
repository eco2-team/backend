"""SQLAlchemy implementation of transaction manager."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class SqlaTransactionManager:
    """트랜잭션 관리자 SQLAlchemy 구현."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        """트랜잭션을 커밋합니다."""
        await self._session.commit()

    async def rollback(self) -> None:
        """트랜잭션을 롤백합니다."""
        await self._session.rollback()
