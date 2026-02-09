"""Eval Pipeline 도메인 예외.

평가 파이프라인에서 발생하는 비즈니스 규칙 위반을 정의합니다.
"""

from chat_worker.domain.exceptions.base import DomainError


class InvalidBARSScoreError(DomainError):
    """BARS 1-5 범위 위반.

    AxisScore 생성 시 score가 1-5 범위를 벗어나거나,
    evidence가 비어있는 경우 발생합니다.
    """

    def __init__(self, message: str = "Invalid BARS score") -> None:
        super().__init__(message)


class InvalidGradeError(DomainError):
    """유효하지 않은 등급.

    EvalGrade 변환 시 유효하지 않은 값이 입력된 경우 발생합니다.
    """

    def __init__(self, message: str = "Invalid eval grade") -> None:
        super().__init__(message)


class InvalidContinuousScoreError(DomainError):
    """유효하지 않은 연속 점수.

    ContinuousScore 생성 시 value가 0-100 범위를 벗어나는 경우 발생합니다.
    """

    def __init__(self, message: str = "Invalid continuous score") -> None:
        super().__init__(message)


class InvalidCalibrationSampleError(DomainError):
    """유효하지 않은 Calibration 샘플.

    CalibrationSample 생성 시 annotator_agreement가 음수인 경우 발생합니다.
    """

    def __init__(self, message: str = "Invalid calibration sample") -> None:
        super().__init__(message)
