"""Eval Pipeline Exceptions.

Eval 파이프라인에서 발생하는 애플리케이션 레이어 예외.

참조:
- docs/plans/chat-eval-pipeline-plan.md Section A.5
- domain/exceptions/base.py (DomainError)

계층 구조:
- Exception
  - ApplicationError (애플리케이션 레이어 기반)
    - EvalTimeoutError (평가 타임아웃)
    - MaxRegenerationReachedError (재생성 횟수 초과)
    - CalibrationDriftError (Calibration 기준 이동)
"""

from __future__ import annotations


class ApplicationError(Exception):
    """애플리케이션 레이어 UseCase 실행 오류.

    도메인 레이어의 DomainError와 분리된 애플리케이션 전용 기반 예외.
    Presentation 레이어에서 HTTP 응답으로 변환됩니다.
    """

    def __init__(self, message: str = "Application error occurred") -> None:
        self.message = message
        super().__init__(message)


class EvalTimeoutError(ApplicationError):
    """Eval 파이프라인 타임아웃.

    sync 모드에서 L1 Code Grader가 50ms 임계치를 초과하거나,
    async 모드에서 LLM Grader 호출이 타임아웃된 경우.

    Attributes:
        timeout_ms: 설정된 타임아웃 (밀리초)
        elapsed_ms: 실제 소요 시간 (밀리초)
        layer: 타임아웃 발생 레이어 ("code_grader" | "llm_grader" | "calibration")
    """

    def __init__(
        self,
        timeout_ms: float,
        elapsed_ms: float,
        layer: str = "unknown",
    ) -> None:
        self.timeout_ms = timeout_ms
        self.elapsed_ms = elapsed_ms
        self.layer = layer
        super().__init__(
            f"Eval timeout in {layer}: {elapsed_ms:.0f}ms " f"exceeded {timeout_ms:.0f}ms limit"
        )


class MaxRegenerationReachedError(ApplicationError):
    """재생성 횟수 초과.

    sync 모드에서 C등급 판정 후 재생성을 시도했으나,
    최대 허용 재생성 횟수(1회)를 이미 소진한 경우.

    Attributes:
        max_retries: 최대 재생성 허용 횟수
        current_retry: 현재 재생성 시도 횟수
        last_grade: 마지막 평가 등급
    """

    def __init__(
        self,
        max_retries: int = 1,
        current_retry: int = 1,
        last_grade: str = "C",
    ) -> None:
        self.max_retries = max_retries
        self.current_retry = current_retry
        self.last_grade = last_grade
        super().__init__(
            f"Max regeneration reached: {current_retry}/{max_retries} "
            f"(last grade: {last_grade})"
        )


class CalibrationDriftError(ApplicationError):
    """Calibration 기준 이동(Drift) 감지.

    CUSUM 알고리즘으로 탐지된 Calibration Drift.
    모델/프롬프트 변경 후 평가 기준이 이동하여
    기존 Calibration Set과 불일치.

    Attributes:
        axis: drift가 발생한 평가 축
        cusum_value: CUSUM 통계량
        threshold: drift 판정 임계치
        direction: drift 방향 ("positive" | "negative")
    """

    def __init__(
        self,
        axis: str,
        cusum_value: float,
        threshold: float,
        direction: str = "unknown",
    ) -> None:
        self.axis = axis
        self.cusum_value = cusum_value
        self.threshold = threshold
        self.direction = direction
        super().__init__(
            f"Calibration drift detected on '{axis}': "
            f"CUSUM={cusum_value:.3f} (threshold={threshold:.3f}, "
            f"direction={direction})"
        )


__all__ = [
    "ApplicationError",
    "EvalTimeoutError",
    "MaxRegenerationReachedError",
    "CalibrationDriftError",
]
