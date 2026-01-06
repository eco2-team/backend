"""NormalizedSite Entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from location.domain.value_objects import Coordinates


@dataclass(frozen=True)
class NormalizedSite:
    """정규화된 위치 엔티티.

    다양한 소스(공공데이터, 제로웨이스트 등)에서 수집한 위치 정보를
    정규화한 불변 엔티티입니다.
    """

    id: int
    source: str
    source_key: str
    positn_nm: str | None = None
    positn_rgn_nm: str | None = None
    positn_lotno_addr: str | None = None
    positn_rdnm_addr: str | None = None
    positn_pstn_add_expln: str | None = None
    positn_pstn_lat: float | None = None
    positn_pstn_lot: float | None = None
    positn_intdc_cn: str | None = None
    positn_cnvnc_fclt_srvc_expln: str | None = None
    mon_sals_hr_expln_cn: str | None = None
    tues_sals_hr_expln_cn: str | None = None
    wed_sals_hr_expln_cn: str | None = None
    thur_sals_hr_expln_cn: str | None = None
    fri_sals_hr_expln_cn: str | None = None
    sat_sals_hr_expln_cn: str | None = None
    sun_sals_hr_expln_cn: str | None = None
    lhldy_sals_hr_expln_cn: str | None = None
    lhldy_dyoff_cn: str | None = None
    tmpr_lhldy_cn: str | None = None
    clct_item_cn: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def coordinates(self) -> Coordinates | None:
        """좌표 Value Object를 반환합니다."""
        if self.positn_pstn_lat is None or self.positn_pstn_lot is None:
            return None
        return Coordinates(latitude=self.positn_pstn_lat, longitude=self.positn_pstn_lot)
