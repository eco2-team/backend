"""Eval Result Command Gateway Port - 평가 결과 저장 (CQS: Command).

Clean Architecture:
- Port: 이 파일 (추상화, Application Layer)
- Adapter: infrastructure/persistence/eval/ (구현체)

Convention Decision (A.4):
- 신규 포트는 Protocol 사용 (structural subtyping, 테스트 용이)
- 기존 포트(ABC)는 별도 마이그레이션 PR에서 전환 예정

CQS(Command-Query Separation) 패턴:
- Command: 이 파일 (저장/변경)
- Query: eval_result_query_gateway.py (조회)

참조: docs/plans/chat-eval-pipeline-plan.md Section 5.1
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from chat_worker.application.dto.eval_result import EvalResult


@runtime_checkable
class EvalResultCommandGateway(Protocol):
    """Eval 결과 저장 Gateway (CQS: Command).

    평가 결과 영속화 및 Calibration Drift 로그 저장.
    Layered Memory 패턴 적용으로 계층적 저장.
    """

    async def save_result(self, eval_result: "EvalResult") -> None:
        """평가 결과 저장.

        Args:
            eval_result: 평가 결과 DTO
        """
        ...

    async def save_drift_log(self, drift_entry: dict) -> None:
        """Calibration Drift 로그 저장.

        CUSUM 알고리즘에서 탐지된 drift 정보를 기록.

        Args:
            drift_entry: drift 탐지 정보 (axis, cusum_value, timestamp 등)
        """
        ...
