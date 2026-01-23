"""SQLAlchemy Location Reader Implementation."""

from __future__ import annotations

import json
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from location.application.nearby.ports import LocationReader
from location.domain.entities import NormalizedSite
from location.infrastructure.persistence_postgres.models import NormalizedLocationSite


class SqlaLocationReader(LocationReader):
    """SQLAlchemy 기반 위치 Reader.

    LocationReader Port를 구현합니다.
    PostGIS earth_distance 또는 Haversine fallback을 사용합니다.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize.

        Args:
            session: SQLAlchemy 비동기 세션
        """
        self._session = session

    async def find_within_radius(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
        limit: int,
    ) -> Sequence[tuple[NormalizedSite, float]]:
        """주어진 좌표에서 반경 내 위치를 조회합니다."""
        try:
            distance_expr = self._earthdistance_expr(latitude, longitude)
            return await self._execute_distance_query(distance_expr, radius_km, limit)
        except DBAPIError:
            distance_expr = self._haversine_expr(latitude, longitude)
            return await self._execute_distance_query(distance_expr, radius_km, limit)

    async def find_by_id(self, site_id: int) -> NormalizedSite | None:
        """ID로 사이트를 조회합니다."""
        query = select(NormalizedLocationSite).where(NormalizedLocationSite.positn_sn == site_id)
        result = await self._session.execute(query)
        site = result.scalar_one_or_none()
        if site is None:
            return None
        return self._to_domain(site)

    async def count_sites(self) -> int:
        """전체 사이트 수를 반환합니다."""
        result = await self._session.execute(
            select(func.count()).select_from(NormalizedLocationSite)
        )
        return int(result.scalar_one())

    async def _execute_distance_query(
        self,
        distance_expr,
        radius_km: float,
        limit: int,
    ) -> list[tuple[NormalizedSite, float]]:
        """거리 쿼리를 실행합니다."""
        query = (
            select(NormalizedLocationSite, distance_expr)
            .where(
                NormalizedLocationSite.positn_pstn_lat.is_not(None),
                NormalizedLocationSite.positn_pstn_lot.is_not(None),
                distance_expr <= radius_km,
            )
            .order_by(distance_expr.asc())
            .limit(limit)
        )
        result = await self._session.execute(query)
        rows: list[tuple[NormalizedSite, float]] = []
        for site, distance_km in result.all():
            if distance_km is None:
                continue
            rows.append((self._to_domain(site), float(distance_km)))
        return rows

    def _to_domain(self, site: NormalizedLocationSite) -> NormalizedSite:
        """ORM 모델을 도메인 엔티티로 변환합니다."""
        metadata = {}
        if site.source_metadata:
            try:
                metadata = json.loads(site.source_metadata)
            except (TypeError, json.JSONDecodeError):
                metadata = {}
        return NormalizedSite(
            id=int(site.positn_sn),
            source=site.source,
            source_key=site.source_pk,
            positn_nm=site.positn_nm,
            positn_rgn_nm=site.positn_rgn_nm,
            positn_lotno_addr=site.positn_lotno_addr,
            positn_rdnm_addr=site.positn_rdnm_addr,
            positn_pstn_add_expln=site.positn_pstn_add_expln,
            positn_pstn_lat=site.positn_pstn_lat,
            positn_pstn_lot=site.positn_pstn_lot,
            positn_intdc_cn=site.positn_intdc_cn,
            positn_cnvnc_fclt_srvc_expln=site.positn_cnvnc_fclt_srvc_expln,
            mon_sals_hr_expln_cn=site.mon_sals_hr_expln_cn,
            tues_sals_hr_expln_cn=site.tues_sals_hr_expln_cn,
            wed_sals_hr_expln_cn=site.wed_sals_hr_expln_cn,
            thur_sals_hr_expln_cn=site.thur_sals_hr_expln_cn,
            fri_sals_hr_expln_cn=site.fri_sals_hr_expln_cn,
            sat_sals_hr_expln_cn=site.sat_sals_hr_expln_cn,
            sun_sals_hr_expln_cn=site.sun_sals_hr_expln_cn,
            lhldy_sals_hr_expln_cn=site.lhldy_sals_hr_expln_cn,
            lhldy_dyoff_cn=site.lhldy_dyoff_cn,
            tmpr_lhldy_cn=site.tmpr_lhldy_cn,
            clct_item_cn=site.clct_item_cn,
            metadata=metadata,
        )

    @staticmethod
    def _earthdistance_expr(latitude: float, longitude: float):
        """PostGIS earth_distance 표현식."""
        return (
            func.earth_distance(
                func.ll_to_earth(latitude, longitude),
                func.ll_to_earth(
                    NormalizedLocationSite.positn_pstn_lat,
                    NormalizedLocationSite.positn_pstn_lot,
                ),
            )
            / 1000.0
        ).label("distance_km")

    @staticmethod
    def _haversine_expr(latitude: float, longitude: float):
        """Haversine 공식 표현식 (fallback)."""
        cosine = func.cos(func.radians(latitude)) * func.cos(
            func.radians(NormalizedLocationSite.positn_pstn_lat)
        ) * func.cos(
            func.radians(NormalizedLocationSite.positn_pstn_lot) - func.radians(longitude)
        ) + func.sin(
            func.radians(latitude)
        ) * func.sin(
            func.radians(NormalizedLocationSite.positn_pstn_lat)
        )
        clamped = func.least(1.0, func.greatest(-1.0, cosine))
        return (6371.0 * func.acos(clamped)).label("distance_km")
