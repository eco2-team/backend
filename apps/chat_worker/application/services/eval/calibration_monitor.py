"""Calibration Monitor Service - L3 Calibration Drift 감지.

Swiss Cheese Layer 3: CUSUM 알고리즘 기반 평가 기준 이동(drift) 감지.
Calibration Set과 실시간 평가 결과의 괴리를 모니터링합니다.

CUSUM (Cumulative Sum) 알고리즘:
- 양방향 누적합(S⁺, S⁻) 산출
- 임계치 초과 시 drift 경고/위험 판정
- 축별 독립 감시

Clean Architecture:
- Service: 이 파일 (Port 의존)
- Command: EvaluateResponseCommand에서 주기적 호출

참조: docs/plans/chat-eval-pipeline-plan.md Section 3.3
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chat_worker.application.ports.eval.bars_evaluator import BARSEvaluator
    from chat_worker.application.ports.eval.calibration_data_gateway import (
        CalibrationDataGateway,
    )
    from chat_worker.application.ports.eval.eval_result_query_gateway import (
        EvalResultQueryGateway,
    )

logger = logging.getLogger(__name__)

# ── CUSUM 상수 ────────────────────────────────────────────────────────────────
# Reference: Montgomery, "Introduction to Statistical Quality Control", Ch.9
# CUSUM chart parameters tuned for BARS 1-5 scale evaluation scores.
#
# Design Decision: z-score 정규화 대신 raw score 기반 CUSUM 사용.
# 이유: BARS 1-5 척도는 고정 범위이므로 σ가 일정(≈0.8~1.2)하고,
# raw score 기반 임계치(k=0.5, h=4.0)가 충분히 보정됨.
# 향후 축별 baseline_std가 크게 달라지면 z-score 정규화로 전환.

# CRITICAL: h=4.0 (~3σ 수준). 40 steps에서 0.1/step drift 감지.
_CUSUM_CRITICAL_THRESHOLD: float = 4.0
# WARNING: h*0.6 = 2.4 (~2σ 수준). 조기 경보용.
_CUSUM_WARNING_THRESHOLD: float = 2.4

# 기대 평균 (BARS 1-5 척도 중앙값 3.0)
_EXPECTED_MEAN: float = 3.0

# 슬랙(allowance) k=0.5: 평균에서 0.5 이내 변동은 정상으로 간주
_CUSUM_SLACK: float = 0.5

# 최근 점수 조회 기본 개수 (통계적 유의미성 확보를 위한 최소 표본)
_DEFAULT_RECENT_N: int = 50

# 평가 축 목록
_EVAL_AXES: list[str] = [
    "faithfulness",
    "relevance",
    "completeness",
    "safety",
    "communication",
]

# Drift 심각도
_SEVERITY_OK: str = "OK"
_SEVERITY_WARNING: str = "WARNING"
_SEVERITY_CRITICAL: str = "CRITICAL"

# 집계 상태
STATUS_STABLE: str = "STABLE"
STATUS_DRIFTING: str = "DRIFTING"
STATUS_RECALIBRATING: str = "RECALIBRATING"


class CalibrationMonitorService:
    """L3 Calibration Drift Monitor.

    CUSUM 알고리즘으로 축별 평가 기준 이동을 감지합니다.
    실시간 점수와 Calibration Set 기대값의 괴리를 누적 추적.

    Port 의존:
    - EvalResultQueryGateway: 최근 점수 조회
    - CalibrationDataGateway: Calibration Set 접근
    - BARSEvaluator: 재교정 시 사용 (현재 미구현)
    """

    def __init__(
        self,
        eval_query_gw: EvalResultQueryGateway,
        calibration_gw: CalibrationDataGateway,
        bars_evaluator: BARSEvaluator,
    ) -> None:
        """Service 초기화.

        Args:
            eval_query_gw: 평가 결과 조회 Gateway
            calibration_gw: Calibration Set 접근 Gateway
            bars_evaluator: BARS 평가기 (재교정 시 사용)
        """
        self._eval_query_gw = eval_query_gw
        self._calibration_gw = calibration_gw
        self._bars_evaluator = bars_evaluator

    async def check_drift(self) -> dict[str, Any]:
        """CUSUM 기반 Calibration Drift 감지.

        각 평가축의 최근 N개 점수에 대해 CUSUM 통계량을 산출하고,
        임계치 초과 여부로 drift 상태를 판정합니다.

        Returns:
            {
                "status": "STABLE" | "DRIFTING" | "RECALIBRATING",
                "axes": {
                    axis: {
                        "severity": "OK" | "WARNING" | "CRITICAL",
                        "cusum_positive": float,
                        "cusum_negative": float,
                        "sample_count": int,
                    }
                },
                "calibration_version": str,
            }
        """
        axes_detail: dict[str, dict[str, Any]] = {}
        overall_status = STATUS_STABLE

        for axis in _EVAL_AXES:
            recent_scores = await self._eval_query_gw.get_recent_scores(
                axis=axis,
                n=_DEFAULT_RECENT_N,
            )

            if not recent_scores:
                axes_detail[axis] = {
                    "severity": _SEVERITY_OK,
                    "cusum_positive": 0.0,
                    "cusum_negative": 0.0,
                    "sample_count": 0,
                }
                continue

            # CUSUM 산출
            cusum_pos, cusum_neg = self._compute_cusum(recent_scores)
            severity = self._classify_severity(cusum_pos, cusum_neg)

            axes_detail[axis] = {
                "severity": severity,
                "cusum_positive": round(cusum_pos, 4),
                "cusum_negative": round(cusum_neg, 4),
                "sample_count": len(recent_scores),
            }

            # 전체 상태 결정 (가장 심각한 축 기준)
            if severity == _SEVERITY_CRITICAL:
                overall_status = STATUS_DRIFTING
            elif severity == _SEVERITY_WARNING and overall_status == STATUS_STABLE:
                overall_status = STATUS_DRIFTING

        # Calibration 버전 조회
        try:
            calibration_version = await self._calibration_gw.get_calibration_version()
        except Exception:
            calibration_version = "unknown"

        result = {
            "status": overall_status,
            "axes": axes_detail,
            "calibration_version": calibration_version,
        }

        logger.info(
            "Calibration drift check completed",
            extra={
                "status": overall_status,
                "axis_severities": {
                    axis: detail["severity"] for axis, detail in axes_detail.items()
                },
            },
        )

        return result

    async def check_coverage(self) -> dict[str, Any]:
        """Calibration Set의 Intent 커버리지 검증.

        실제 트래픽의 Intent 분포와 Calibration Set의 Intent 집합을 비교하여
        Calibration Set의 대표성을 확인합니다.

        Returns:
            {
                "covered_intents": list[str],
                "uncovered_intents": list[str],
                "coverage_ratio": float,
                "traffic_distribution": dict[str, float],
            }
        """
        # 실제 트래픽 분포 조회
        traffic_dist = await self._eval_query_gw.get_intent_distribution(days=7)

        # Calibration Set Intent 집합 조회
        calibration_intents = await self._calibration_gw.get_calibration_intent_set()

        traffic_intents = set(traffic_dist.keys())
        covered = traffic_intents & calibration_intents
        uncovered = traffic_intents - calibration_intents

        coverage_ratio = len(covered) / len(traffic_intents) if traffic_intents else 1.0

        result: dict[str, Any] = {
            "covered_intents": sorted(covered),
            "uncovered_intents": sorted(uncovered),
            "coverage_ratio": round(coverage_ratio, 4),
            "traffic_distribution": traffic_dist,
        }

        logger.info(
            "Calibration coverage check completed",
            extra={
                "coverage_ratio": coverage_ratio,
                "uncovered_count": len(uncovered),
            },
        )

        return result

    @staticmethod
    def _compute_cusum(scores: list[float]) -> tuple[float, float]:
        """CUSUM 양방향 누적합 산출.

        S⁺(i) = max(0, S⁺(i-1) + (x_i - μ₀ - k))
        S⁻(i) = max(0, S⁻(i-1) + (μ₀ - x_i - k))

        여기서:
        - μ₀: 기대 평균 (_EXPECTED_MEAN)
        - k: 슬랙 파라미터 (_CUSUM_SLACK)

        Args:
            scores: 최근 점수 리스트

        Returns:
            (cusum_positive, cusum_negative) 최종 누적합
        """
        cusum_pos = 0.0
        cusum_neg = 0.0

        for x in scores:
            cusum_pos = max(0.0, cusum_pos + (x - _EXPECTED_MEAN - _CUSUM_SLACK))
            cusum_neg = max(0.0, cusum_neg + (_EXPECTED_MEAN - x - _CUSUM_SLACK))

        return cusum_pos, cusum_neg

    @staticmethod
    def _classify_severity(cusum_pos: float, cusum_neg: float) -> str:
        """CUSUM 값으로 drift 심각도 분류.

        Args:
            cusum_pos: 양방향 CUSUM (상향 drift)
            cusum_neg: 음방향 CUSUM (하향 drift)

        Returns:
            심각도 문자열 ("OK" | "WARNING" | "CRITICAL")
        """
        max_cusum = max(cusum_pos, cusum_neg)

        if max_cusum >= _CUSUM_CRITICAL_THRESHOLD:
            return _SEVERITY_CRITICAL
        if max_cusum >= _CUSUM_WARNING_THRESHOLD:
            return _SEVERITY_WARNING
        return _SEVERITY_OK


__all__ = ["CalibrationMonitorService"]
