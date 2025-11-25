from __future__ import annotations

from typing import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domains.location.models import KecoRecycleSite


class KecoRepository:
    """Simple read-only repository for KECO recycle sites."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(self, limit: int | None = None) -> Sequence[KecoRecycleSite]:
        query = select(KecoRecycleSite).order_by(KecoRecycleSite.positn_sn.asc())
        if limit:
            query = query.limit(limit)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_by_ids(self, ids: Iterable[int]) -> Sequence[KecoRecycleSite]:
        query = (
            select(KecoRecycleSite)
            .where(KecoRecycleSite.positn_sn.in_(list(ids)))
            .order_by(KecoRecycleSite.positn_sn.asc())
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_sites(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(KecoRecycleSite))
        return int(result.scalar_one())
