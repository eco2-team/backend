"""CalibrationMonitorService Unit Tests."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from chat_worker.application.services.eval.calibration_monitor import (
    CalibrationMonitorService,
    STATUS_DRIFTING,
    STATUS_STABLE,
)


# ── 테스트 헬퍼 ──────────────────────────────────────────────────────────────


def _make_service(
    eval_query_gw: AsyncMock | None = None,
    calibration_gw: AsyncMock | None = None,
    bars_evaluator: AsyncMock | None = None,
) -> CalibrationMonitorService:
    """CalibrationMonitorService 팩토리 (3개 Port mock)."""
    return CalibrationMonitorService(
        eval_query_gw=eval_query_gw or AsyncMock(),
        calibration_gw=calibration_gw or AsyncMock(),
        bars_evaluator=bars_evaluator or AsyncMock(),
    )


@pytest.mark.eval_unit
class TestCalibrationMonitorCheckDrift:
    """CalibrationMonitorService.check_drift() 테스트."""

    async def test_all_stable_returns_stable(self) -> None:
        """모든 축이 기대 평균(3.0) 근처 -> STABLE 상태."""
        eval_query_gw = AsyncMock()
        # 모든 축에 대해 기대 평균(3.0) 근처 점수 반환
        eval_query_gw.get_recent_scores.return_value = [3.0, 3.1, 2.9, 3.0, 3.2] * 10

        calibration_gw = AsyncMock()
        calibration_gw.get_calibration_version.return_value = "v1.0-2026-02-01"

        service = _make_service(eval_query_gw=eval_query_gw, calibration_gw=calibration_gw)

        result = await service.check_drift()

        assert result["status"] == STATUS_STABLE
        assert result["calibration_version"] == "v1.0-2026-02-01"
        # 5개 축 모두 존재
        assert len(result["axes"]) == 5
        for axis_detail in result["axes"].values():
            assert axis_detail["severity"] == "OK"

    async def test_drift_detected_returns_drifting(self) -> None:
        """점수가 지속적으로 높으면 CUSUM 양방향 누적으로 DRIFTING 감지."""
        eval_query_gw = AsyncMock()

        # 기대 평균 3.0, 슬랙 0.5 -> x > 3.5일 때 양의 누적
        # 4.5 점수를 지속: 누적 = (4.5 - 3.0 - 0.5) = 1.0 per step
        # 50개 점수 -> cusum_pos = 50.0 (>> 5.0 임계치)
        high_scores = [4.5] * 50

        async def get_recent_scores(axis: str, n: int = 10) -> list[float]:
            if axis == "faithfulness":
                return high_scores
            # 나머지 축은 정상
            return [3.0, 3.1, 2.9, 3.0, 3.2] * 10

        eval_query_gw.get_recent_scores.side_effect = get_recent_scores

        calibration_gw = AsyncMock()
        calibration_gw.get_calibration_version.return_value = "v1.0"

        service = _make_service(eval_query_gw=eval_query_gw, calibration_gw=calibration_gw)

        result = await service.check_drift()

        assert result["status"] == STATUS_DRIFTING
        assert result["axes"]["faithfulness"]["severity"] == "CRITICAL"
        assert result["axes"]["faithfulness"]["cusum_positive"] > 5.0

    async def test_warning_level_drift_detected(self) -> None:
        """CUSUM WARNING 수준 drift 감지 (3.0 <= cusum < 5.0)."""
        eval_query_gw = AsyncMock()

        # 기대 평균 3.0, 슬랙 0.5 -> x=3.8일 때 누적 = (3.8-3.0-0.5) = 0.3/step
        # 12개 점수 -> cusum_pos = 3.6 (WARNING: >= 3.0, < 5.0 CRITICAL)
        warning_scores = [3.8] * 12

        async def get_recent_scores(axis: str, n: int = 10) -> list[float]:
            if axis == "relevance":
                return warning_scores
            return [3.0, 3.1, 2.9, 3.0, 3.2] * 10

        eval_query_gw.get_recent_scores.side_effect = get_recent_scores

        calibration_gw = AsyncMock()
        calibration_gw.get_calibration_version.return_value = "v1.0"

        service = _make_service(eval_query_gw=eval_query_gw, calibration_gw=calibration_gw)

        result = await service.check_drift()

        assert result["status"] == STATUS_DRIFTING
        assert result["axes"]["relevance"]["severity"] == "WARNING"
        cusum_pos = result["axes"]["relevance"]["cusum_positive"]
        assert 3.0 <= cusum_pos < 5.0

    async def test_empty_scores_returns_stable(self) -> None:
        """점수가 없으면(빈 리스트) 모든 축이 OK -> STABLE."""
        eval_query_gw = AsyncMock()
        eval_query_gw.get_recent_scores.return_value = []

        calibration_gw = AsyncMock()
        calibration_gw.get_calibration_version.return_value = "v1.0"

        service = _make_service(eval_query_gw=eval_query_gw, calibration_gw=calibration_gw)

        result = await service.check_drift()

        assert result["status"] == STATUS_STABLE
        for axis_detail in result["axes"].values():
            assert axis_detail["severity"] == "OK"
            assert axis_detail["cusum_positive"] == 0.0
            assert axis_detail["cusum_negative"] == 0.0
            assert axis_detail["sample_count"] == 0


@pytest.mark.eval_unit
class TestCalibrationMonitorCheckCoverage:
    """CalibrationMonitorService.check_coverage() 테스트."""

    async def test_check_coverage_no_gaps(self) -> None:
        """트래픽 intent가 모두 Calibration Set에 포함 -> 커버리지 100%."""
        eval_query_gw = AsyncMock()
        eval_query_gw.get_intent_distribution.return_value = {
            "waste": 0.45,
            "general": 0.30,
            "location": 0.15,
            "bulk_waste": 0.10,
        }

        calibration_gw = AsyncMock()
        calibration_gw.get_calibration_intent_set.return_value = {
            "waste",
            "general",
            "location",
            "bulk_waste",
            "weather",
        }

        service = _make_service(eval_query_gw=eval_query_gw, calibration_gw=calibration_gw)

        result = await service.check_coverage()

        assert result["coverage_ratio"] == 1.0
        assert len(result["uncovered_intents"]) == 0
        assert set(result["covered_intents"]) == {
            "waste",
            "general",
            "location",
            "bulk_waste",
        }

    async def test_check_coverage_with_gap(self) -> None:
        """트래픽 intent 중 일부가 Calibration Set에 없음 -> 갭 감지."""
        eval_query_gw = AsyncMock()
        eval_query_gw.get_intent_distribution.return_value = {
            "waste": 0.40,
            "general": 0.30,
            "location": 0.15,
            "web_search": 0.10,
            "image_generation": 0.05,
        }

        calibration_gw = AsyncMock()
        calibration_gw.get_calibration_intent_set.return_value = {
            "waste",
            "general",
            "location",
        }

        service = _make_service(eval_query_gw=eval_query_gw, calibration_gw=calibration_gw)

        result = await service.check_coverage()

        assert result["coverage_ratio"] < 1.0
        assert result["coverage_ratio"] == round(3 / 5, 4)
        assert sorted(result["uncovered_intents"]) == [
            "image_generation",
            "web_search",
        ]
        assert sorted(result["covered_intents"]) == [
            "general",
            "location",
            "waste",
        ]
