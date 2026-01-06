"""Test fixtures for location tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from location.domain.entities import NormalizedSite


@pytest.fixture
def mock_location_reader() -> AsyncMock:
    """LocationReader mock."""
    reader = AsyncMock()
    reader.find_within_radius = AsyncMock(return_value=[])
    reader.count_sites = AsyncMock(return_value=0)
    return reader


@pytest.fixture
def sample_site() -> NormalizedSite:
    """테스트용 NormalizedSite."""
    return NormalizedSite(
        id=1,
        source="keco",
        source_key="KECO-001",
        positn_nm="서울 재활용 센터",
        positn_rgn_nm="서울특별시",
        positn_lotno_addr="서울시 강남구 역삼동 123",
        positn_rdnm_addr="서울시 강남구 테헤란로 123",
        positn_pstn_add_expln="역삼역 3번 출구",
        positn_pstn_lat=37.5665,
        positn_pstn_lot=126.978,
        positn_intdc_cn="재활용 수거 센터입니다",
        positn_cnvnc_fclt_srvc_expln="주차 가능",
        mon_sals_hr_expln_cn="09:00 ~ 18:00",
        tues_sals_hr_expln_cn="09:00 ~ 18:00",
        wed_sals_hr_expln_cn="09:00 ~ 18:00",
        thur_sals_hr_expln_cn="09:00 ~ 18:00",
        fri_sals_hr_expln_cn="09:00 ~ 18:00",
        sat_sals_hr_expln_cn="휴무",
        sun_sals_hr_expln_cn="휴무",
        clct_item_cn="무색페트, 캔, 종이",
        metadata={
            "display1": "서울 재활용 센터",
            "display2": "서울시 강남구 테헤란로 123",
            "clctItemCn": "무색페트, 캔, 종이",
        },
    )


@pytest.fixture
def sample_zerowaste_site() -> NormalizedSite:
    """테스트용 제로웨이스트 사이트."""
    return NormalizedSite(
        id=2,
        source="zerowaste",
        source_key="ZW-001",
        positn_nm="알맹상점",
        positn_rgn_nm="서울특별시",
        positn_rdnm_addr="서울시 마포구 연남동 123",
        positn_pstn_lat=37.5601,
        positn_pstn_lot=126.9258,
        positn_intdc_cn="제로웨이스트 리필샵입니다",
        metadata={
            "display1": "알맹상점",
            "memo": "리필 전문점",
        },
    )


@pytest.fixture
def sample_metadata() -> dict[str, Any]:
    """테스트용 메타데이터."""
    return {
        "display1": "서울 재활용 센터",
        "display2": "서울시 강남구 테헤란로 123",
        "clctItemCn": "무색페트, 캔, 종이",
        "bscTelnoCn": "02-1234-5678",
    }
