"""Eval Result DTO.

응답 품질 평가 결과를 담는 Data Transfer Object.
Swiss Cheese 3-Tier Grader (Code + LLM + Calibration) 결과 통합.

참조: docs/plans/chat-eval-pipeline-plan.md Section 5.2

등급 기준:
- S: >= 90 (탁월) - No regeneration
- A: 75-89 (우수) - No regeneration
- B: 55-74 (보통) - 로그만
- C: < 55 (미흡) - Regeneration (sync 모드, 1회)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class EvalResult:
    """응답 품질 평가 결과 (BARS 5-Axis 통합).

    Swiss Cheese 3-Tier Grader의 모든 레이어 결과를 통합.

    Attributes:
        continuous_score: 0-100 연속 점수 (비대칭 가중 합산)
        axis_scores: 축별 평가 결과 {axis -> {score, evidence, reasoning}}
        grade: 등급 (EvalGrade.value: S/A/B/C)
        information_loss: 연속->등급 변환 시 정보 손실률
        grade_confidence: 등급 판정 신뢰도
        code_grader_result: L1 Code Grader 결과 (dict)
        llm_grader_result: L2 LLM Grader 결과 (dict, 없으면 None)
        calibration_status: L3 Calibration 상태 ("STABLE" | "DRIFTING" | "RECALIBRATING" | None)
        model_version: 평가에 사용된 모델 ID
        prompt_version: 루브릭 git SHA
        eval_duration_ms: 평가 소요 시간 (밀리초)
        eval_cost_usd: 평가 비용 (USD, LLM 미사용 시 None)
        metadata: 추가 메타데이터
    """

    continuous_score: float
    axis_scores: dict[str, dict[str, Any]]
    grade: str
    information_loss: float
    grade_confidence: float
    code_grader_result: dict[str, Any] | None
    llm_grader_result: dict[str, Any] | None
    calibration_status: str | None
    model_version: str
    prompt_version: str
    eval_duration_ms: int
    eval_cost_usd: float | None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """직렬화용 딕셔너리 변환."""
        return {
            "continuous_score": self.continuous_score,
            "axis_scores": self.axis_scores,
            "grade": self.grade,
            "information_loss": self.information_loss,
            "grade_confidence": self.grade_confidence,
            "code_grader_result": self.code_grader_result,
            "llm_grader_result": self.llm_grader_result,
            "calibration_status": self.calibration_status,
            "model_version": self.model_version,
            "prompt_version": self.prompt_version,
            "eval_duration_ms": self.eval_duration_ms,
            "eval_cost_usd": self.eval_cost_usd,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvalResult":
        """딕셔너리에서 EvalResult 생성.

        Args:
            data: 직렬화된 평가 결과

        Returns:
            EvalResult 인스턴스
        """
        return cls(
            continuous_score=data["continuous_score"],
            axis_scores=data.get("axis_scores", {}),
            grade=data["grade"],
            information_loss=data.get("information_loss", 0.0),
            grade_confidence=data.get("grade_confidence", 0.0),
            code_grader_result=data.get("code_grader_result"),
            llm_grader_result=data.get("llm_grader_result"),
            calibration_status=data.get("calibration_status"),
            model_version=data.get("model_version", "unknown"),
            prompt_version=data.get("prompt_version", "unknown"),
            eval_duration_ms=data.get("eval_duration_ms", 0),
            eval_cost_usd=data.get("eval_cost_usd"),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def code_only(
        cls,
        code_result_dict: dict[str, Any],
        continuous_score: float,
        grade: str,
        model_version: str = "none",
        prompt_version: str = "none",
        eval_duration_ms: int = 0,
    ) -> "EvalResult":
        """L1 Code Grader 결과만으로 생성 (degraded mode).

        LLM Grader 비활성화 또는 실패 시 Code Grader만으로 평가 결과 생성.
        graceful degradation 전략.

        Args:
            code_result_dict: CodeGraderResult.to_dict() 결과
            continuous_score: Code Grader 기반 연속 점수
            grade: 등급 문자열 (EvalGrade.value)
            model_version: 모델 버전 (Code-only이므로 기본 "none")
            prompt_version: 프롬프트 버전 (Code-only이므로 기본 "none")
            eval_duration_ms: 평가 소요 시간

        Returns:
            EvalResult 인스턴스 (LLM/Calibration 필드 None)
        """
        return cls(
            continuous_score=continuous_score,
            axis_scores={},
            grade=grade,
            information_loss=0.0,
            grade_confidence=0.5,
            code_grader_result=code_result_dict,
            llm_grader_result=None,
            calibration_status=None,
            model_version=model_version,
            prompt_version=prompt_version,
            eval_duration_ms=eval_duration_ms,
            eval_cost_usd=None,
            metadata={"mode": "code_only", "degraded": True},
        )

    @classmethod
    def failed(cls, reason: str) -> "EvalResult":
        """평가 실패 시 기본값 생성.

        평가 파이프라인 자체가 실패했을 때의 안전한 기본값.
        응답 자체는 사용자에게 전달 (eval 실패가 응답 차단하면 안 됨).

        Args:
            reason: 실패 사유

        Returns:
            EvalResult 인스턴스 (기본값, B등급 처리)
        """
        return cls(
            continuous_score=65.0,
            axis_scores={},
            grade="B",
            information_loss=0.0,
            grade_confidence=0.0,
            code_grader_result=None,
            llm_grader_result=None,
            calibration_status=None,
            model_version="unknown",
            prompt_version="unknown",
            eval_duration_ms=0,
            eval_cost_usd=None,
            metadata={
                "mode": "failed",
                "failure_reason": reason,
                "timestamp": datetime.now(tz=UTC).isoformat(),
            },
        )


__all__ = ["EvalResult"]
