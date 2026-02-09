"""Calibration Data Gateway Port - Calibration Set 접근 추상화.

Clean Architecture:
- Port: 이 파일 (추상화, Application Layer)
- Adapter: infrastructure/persistence/eval/ (구현체)

Convention Decision (A.4):
- 신규 포트는 Protocol 사용 (structural subtyping, 테스트 용이)
- 기존 포트(ABC)는 별도 마이그레이션 PR에서 전환 예정

Calibration Set:
- 최소 2명 독립 어노테이터가 각 축을 개별 채점
- Cohen's kappa >= 0.6 이상이어야 set에 포함
- Intent별 층화 샘플링: 10개 intent x 5-10개 = 50-100개
- 갱신 주기: 2주 또는 모델/프롬프트 변경 시

참조: docs/plans/chat-eval-pipeline-plan.md Section 3.3.1, 5.1
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    # CalibrationSample VO는 Phase 2에서 구현 예정
    # 경로: domain/value_objects/calibration_sample.py
    from chat_worker.domain.value_objects.calibration_sample import CalibrationSample


@runtime_checkable
class CalibrationDataGateway(Protocol):
    """Calibration Set 접근 Gateway.

    Layer 3 Calibration Monitor에서 사용.
    Ground-truth 기반 평가 기준 이동(drift) 감지에 필요한 데이터 제공.
    """

    async def get_calibration_set(self) -> list["CalibrationSample"]:
        """전체 Calibration Set 조회.

        Intent별 층화 샘플링된 50-100개 ground-truth 데이터.
        각 샘플은 최소 2명 어노테이터의 합의(kappa >= 0.6) 결과.

        Returns:
            CalibrationSample 리스트
        """
        ...

    async def get_calibration_version(self) -> str:
        """현재 Calibration Set 버전 조회.

        모델/프롬프트 변경 시 version이 갱신되어
        새로운 calibration 기준이 적용됨을 나타냄.

        Returns:
            버전 문자열 (예: "v2.1-2026-02-01")
        """
        ...

    async def get_calibration_intent_set(self) -> set[str]:
        """현재 Calibration Set에 포함된 Intent 집합 반환.

        B.10 coverage 검증에 사용.
        실제 트래픽의 intent 분포와 비교하여
        calibration set의 대표성을 확인.

        Returns:
            intent 문자열 집합 (예: {"waste", "general", "location", ...})
        """
        ...
