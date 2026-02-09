"""Eval Result Query Gateway Port - 평가 결과 조회 (CQS: Query).

Clean Architecture:
- Port: 이 파일 (추상화, Application Layer)
- Adapter: infrastructure/persistence/eval/ (구현체)

Convention Decision (A.4):
- 신규 포트는 Protocol 사용 (structural subtyping, 테스트 용이)
- 기존 포트(ABC)는 별도 마이그레이션 PR에서 전환 예정

CQS(Command-Query Separation) 패턴:
- Command: eval_result_command_gateway.py (저장/변경)
- Query: 이 파일 (조회)

참조: docs/plans/chat-eval-pipeline-plan.md Section 5.1
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EvalResultQueryGateway(Protocol):
    """Eval 결과 조회 Gateway (CQS: Query).

    Calibration Monitor, 비용 관리, Intent 분포 분석에 사용.
    """

    async def get_recent_scores(self, axis: str, n: int = 10) -> list[float]:
        """특정 축의 최근 N개 점수 조회.

        CUSUM Calibration Drift 감지에 사용.

        Args:
            axis: 평가 축 이름 (faithfulness, relevance 등)
            n: 조회할 최근 점수 개수 (기본 10)

        Returns:
            최근 N개 점수 리스트 (최신순)
        """
        ...

    async def get_daily_cost(self) -> float:
        """당일 평가 비용 합계 조회 (USD).

        비용 예산(eval_cost_budget_daily_usd) 초과 방지에 사용.

        Returns:
            당일 누적 평가 비용 (USD)
        """
        ...

    async def get_intent_distribution(self, days: int = 7) -> dict[str, float]:
        """최근 N일간 Intent별 트래픽 비율 반환.

        B.10 Calibration coverage 검증에 사용.
        Calibration set이 실제 트래픽 분포를 반영하는지 확인.

        Args:
            days: 조회 기간 (일 단위, 기본 7일)

        Returns:
            intent -> 비율 매핑 (예: {"waste": 0.45, "general": 0.30, ...})
        """
        ...
