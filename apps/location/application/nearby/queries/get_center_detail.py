"""Get Center Detail Query.

장소 상세 정보 조회 Query. DB + Kakao 보강.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from location.application.nearby.services import CategoryClassifierService
from location.application.nearby.dto import LocationDetailDTO

if TYPE_CHECKING:
    from location.application.nearby.ports import LocationReader
    from location.application.ports.kakao_local_client import KakaoLocalClientPort

logger = logging.getLogger(__name__)


class GetCenterDetailQuery:
    """장소 상세 조회 Query.

    DB에서 ID로 조회 후 Kakao API로 보강합니다.
    """

    def __init__(
        self,
        location_reader: "LocationReader",
        kakao_client: "KakaoLocalClientPort | None",
    ) -> None:
        self._reader = location_reader
        self._kakao = kakao_client

    async def execute(self, center_id: int) -> LocationDetailDTO | None:
        """장소 상세 정보를 조회합니다.

        Args:
            center_id: 장소 ID

        Returns:
            LocationDetail 또는 None (미발견 시)
        """
        site = await self._reader.find_by_id(center_id)
        if site is None:
            return None

        metadata = site.metadata or {}
        store_category, pickup_categories = CategoryClassifierService.classify(site, metadata)

        # 기본 정보 구성
        name = metadata.get("display1") or site.positn_nm or site.positn_rdnm_addr or ""
        phone = metadata.get("phone") or site.positn_cnvnc_fclt_srvc_expln

        # Kakao API로 보강 (place_url, 전화번호 업데이트)
        place_url = None
        kakao_place_id = None
        if self._kakao and site.positn_nm and site.positn_pstn_lat and site.positn_pstn_lot:
            try:
                response = await self._kakao.search_keyword(
                    query=site.positn_nm,
                    x=site.positn_pstn_lot,
                    y=site.positn_pstn_lat,
                    radius=100,
                    size=1,
                    sort="distance",
                )
                if response.places:
                    matched = response.places[0]
                    place_url = matched.place_url
                    kakao_place_id = matched.id
                    if not phone and matched.phone:
                        phone = matched.phone
            except Exception as e:
                logger.warning("Kakao enrichment failed", extra={"error": str(e)})

        return LocationDetailDTO(
            id=site.id,
            name=name,
            source=site.source,
            road_address=site.positn_rdnm_addr,
            lot_address=site.positn_lotno_addr,
            latitude=site.positn_pstn_lat,
            longitude=site.positn_pstn_lot,
            store_category=(
                store_category.value if hasattr(store_category, "value") else str(store_category)
            ),
            pickup_categories=[
                p.value if hasattr(p, "value") else str(p) for p in (pickup_categories or [])
            ],
            phone=phone,
            place_url=place_url,
            kakao_place_id=kakao_place_id,
            collection_items=site.clct_item_cn,
            introduction=site.positn_intdc_cn,
        )
