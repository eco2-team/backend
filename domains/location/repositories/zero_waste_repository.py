from __future__ import annotations

from typing import Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from domains.location.models import ZeroWasteSite


class ZeroWasteRepository:
    """Reads zero-waste shop data stored via the bootstrap CSV importer."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_within_radius(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_km: float,
        limit: int = 100,
    ) -> Sequence[Tuple[ZeroWasteSite, float]]:
        """Return shops within `radius_km` using the Haversine formula."""

        try:
            distance_expr = self._earthdistance_expr(latitude, longitude)
            return await self._execute_distance_query(distance_expr, radius_km, limit)
        except DBAPIError:
            # fall back to manual query if extensions are missing
            distance_expr = self._haversine_expr(latitude, longitude)
            return await self._execute_distance_query(distance_expr, radius_km, limit)

    async def count_sites(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(ZeroWasteSite))
        return int(result.scalar_one())

    async def _execute_distance_query(
        self,
        distance_expr,
        radius_km: float,
        limit: int,
    ) -> list[Tuple[ZeroWasteSite, float]]:
        query = (
            select(ZeroWasteSite, distance_expr)
            .where(
                ZeroWasteSite.lat.is_not(None),
                ZeroWasteSite.lon.is_not(None),
                distance_expr <= radius_km,
            )
            .order_by(distance_expr.asc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        rows: list[Tuple[ZeroWasteSite, float]] = []
        for site, distance_km in result.all():
            if distance_km is None:
                continue
            rows.append((site, float(distance_km)))
        return rows

    @staticmethod
    def _earthdistance_expr(latitude: float, longitude: float):
        return (
            func.earth_distance(
                func.ll_to_earth(latitude, longitude),
                func.ll_to_earth(ZeroWasteSite.lat, ZeroWasteSite.lon),
            )
            / 1000.0
        ).label("distance_km")

    @staticmethod
    def _haversine_expr(latitude: float, longitude: float):
        cosine = (
            func.cos(func.radians(latitude))
            * func.cos(func.radians(ZeroWasteSite.lat))
            * func.cos(func.radians(ZeroWasteSite.lon) - func.radians(longitude))
            + func.sin(func.radians(latitude)) * func.sin(func.radians(ZeroWasteSite.lat))
        )
        clamped = func.least(1.0, func.greatest(-1.0, cosine))
        return (6371.0 * func.acos(clamped)).label("distance_km")


