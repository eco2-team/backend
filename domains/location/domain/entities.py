from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from domains.location.domain.value_objects import Coordinates


@dataclass(frozen=True)
class NormalizedSite:
    id: int
    source: str
    source_key: str
    positn_nm: Optional[str] = None
    positn_rgn_nm: Optional[str] = None
    positn_lotno_addr: Optional[str] = None
    positn_rdnm_addr: Optional[str] = None
    positn_pstn_add_expln: Optional[str] = None
    positn_pstn_lat: Optional[float] = None
    positn_pstn_lot: Optional[float] = None
    positn_intdc_cn: Optional[str] = None
    positn_cnvnc_fclt_srvc_expln: Optional[str] = None
    mon_sals_hr_expln_cn: Optional[str] = None
    tues_sals_hr_expln_cn: Optional[str] = None
    wed_sals_hr_expln_cn: Optional[str] = None
    thur_sals_hr_expln_cn: Optional[str] = None
    fri_sals_hr_expln_cn: Optional[str] = None
    sat_sals_hr_expln_cn: Optional[str] = None
    sun_sals_hr_expln_cn: Optional[str] = None
    lhldy_sals_hr_expln_cn: Optional[str] = None
    lhldy_dyoff_cn: Optional[str] = None
    tmpr_lhldy_cn: Optional[str] = None
    clct_item_cn: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def coordinates(self) -> Optional[Coordinates]:
        if self.positn_pstn_lat is None or self.positn_pstn_lot is None:
            return None
        return Coordinates(latitude=self.positn_pstn_lat, longitude=self.positn_pstn_lot)
