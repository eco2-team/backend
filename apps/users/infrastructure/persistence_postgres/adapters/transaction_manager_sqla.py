"""SQLAlchemy implementation of transaction manager."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession


class SqlaTransactionManager:
    """트랜잭션 관리자 SQLAlchemy 구현."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        """트랜잭션을 시작하고 컨텍스트 매니저로 관리합니다.

        성공 시 자동 커밋, 예외 발생 시 롤백합니다.
        """
        try:
            yield
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

    async def commit(self) -> None:
        """트랜잭션을 커밋합니다."""
        await self._session.commit()

    async def rollback(self) -> None:
        """트랜잭션을 롤백합니다."""
        await self._session.rollback()
