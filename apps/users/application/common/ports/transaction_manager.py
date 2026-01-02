"""Transaction manager port."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Protocol


class TransactionManager(Protocol):
    """트랜잭션 관리 포트."""

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        """트랜잭션을 시작합니다."""
        ...

    async def commit(self) -> None:
        """트랜잭션을 커밋합니다."""
        ...

    async def rollback(self) -> None:
        """트랜잭션을 롤백합니다."""
        ...
