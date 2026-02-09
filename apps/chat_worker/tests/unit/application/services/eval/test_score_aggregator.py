"""ScoreAggregatorService Unit Tests."""

from __future__ import annotations

import pytest

from chat_worker.application.services.eval.code_grader import CodeGraderResult
from chat_worker.application.services.eval.score_aggregator import ScoreAggregatorService
from chat_worker.domain.value_objects.axis_score import AxisScore


# ── 테스트 헬퍼 ──────────────────────────────────────────────────────────────


def _make_axis_score(axis: str, score: int) -> AxisScore:
    """테스트용 AxisScore 팩토리."""
    return AxisScore(
        axis=axis,
        score=score,
        evidence="테스트 근거 텍스트",
        reasoning="테스트 채점 이유",
    )


def _make_code_result(overall: float = 0.85) -> CodeGraderResult:
    """테스트용 CodeGraderResult 팩토리."""
    return CodeGraderResult(
        scores={
            "format_compliance": 1.0,
            "length_check": 1.0,
            "language_consistency": 1.0,
            "hallucination_keywords": 1.0,
            "citation_presence": 0.5,
            "intent_answer_alignment": 0.6,
        },
        passed={
            "format_compliance": True,
            "length_check": True,
            "language_consistency": True,
            "hallucination_keywords": True,
            "citation_presence": True,
            "intent_answer_alignment": False,
        },
        details={
            "format_compliance": "형식 준수",
            "length_check": "적정 길이",
            "language_consistency": "한국어 비율 양호",
            "hallucination_keywords": "금지 표현 없음",
            "citation_presence": "출처 미포함",
            "intent_answer_alignment": "필수 섹션 누락",
        },
        overall_score=overall,
    )


def _make_full_llm_scores(
    scores: dict[str, int] | None = None,
) -> dict[str, AxisScore]:
    """5축 전체 LLM 점수 생성."""
    default_scores = {
        "faithfulness": 4,
        "relevance": 4,
        "completeness": 4,
        "safety": 5,
        "communication": 4,
    }
    s = scores or default_scores
    return {axis: _make_axis_score(axis, v) for axis, v in s.items()}


@pytest.mark.eval_unit
class TestScoreAggregatorService:
    """ScoreAggregatorService 다층 평가 결과 통합 테스트."""

    def setup_method(self) -> None:
        """테스트 초기화."""
        self.aggregator = ScoreAggregatorService()

    def test_aggregate_with_llm_scores(self) -> None:
        """L1+L2 전체 경로: LLM 점수 포함 통합."""
        code_result = _make_code_result()
        llm_scores = _make_full_llm_scores()

        result = self.aggregator.aggregate(
            code_result=code_result,
            llm_scores=llm_scores,
            intent="general",
            model_version="gpt-4o-mini",
            prompt_version="v1.0",
            eval_duration_ms=150,
        )

        assert result.continuous_score > 0
        assert result.grade in ("S", "A", "B", "C")
        assert result.axis_scores  # 비어있지 않음
        assert result.code_grader_result is not None
        assert result.llm_grader_result is not None
        assert result.model_version == "gpt-4o-mini"
        assert result.prompt_version == "v1.0"
        assert result.eval_duration_ms == 150
        assert result.metadata["mode"] == "full"

    def test_aggregate_code_only(self) -> None:
        """LLM 점수 None: code-only degraded mode."""
        code_result = _make_code_result(overall=0.85)

        result = self.aggregator.aggregate(
            code_result=code_result,
            llm_scores=None,
            intent="general",
        )

        assert result.grade in ("S", "A", "B", "C")
        assert result.continuous_score == round(0.85 * 100, 2)
        assert result.llm_grader_result is None
        assert result.metadata["mode"] == "code_only"
        assert result.metadata["degraded"] is True

    def test_aggregate_empty_llm_scores(self) -> None:
        """LLM 점수 빈 dict: code-only 경로로 처리."""
        code_result = _make_code_result(overall=0.70)

        result = self.aggregator.aggregate(
            code_result=code_result,
            llm_scores={},
            intent="general",
        )

        # 빈 dict도 falsy이므로 code-only 경로
        assert result.continuous_score == round(0.70 * 100, 2)
        assert result.llm_grader_result is None
        assert result.metadata["mode"] == "code_only"

    def test_hazardous_intent_uses_hazardous_weights(self) -> None:
        """waste intent는 Safety 부스트 가중치 사용."""
        code_result = _make_code_result()
        # Safety=5(높음), Communication=1(낮음) -> hazardous에서 유리
        llm_scores = _make_full_llm_scores(
            {
                "faithfulness": 4,
                "relevance": 4,
                "completeness": 4,
                "safety": 5,
                "communication": 1,
            }
        )

        result_hazardous = self.aggregator.aggregate(
            code_result=code_result,
            llm_scores=llm_scores,
            intent="waste",
        )

        result_general = self.aggregator.aggregate(
            code_result=code_result,
            llm_scores=llm_scores,
            intent="general",
        )

        # waste는 safety 가중치 0.25, communication 0.05
        # general은 safety 0.15, communication 0.10
        # Safety=5(100), Communication=1(0) -> hazardous가 더 높은 점수
        assert result_hazardous.continuous_score > result_general.continuous_score
        assert result_hazardous.metadata["intent_weights"] == "hazardous"
        assert result_general.metadata["intent_weights"] == "default"

    def test_grade_s_for_high_scores(self) -> None:
        """모든 축 5점 -> S등급 (>= 90)."""
        code_result = _make_code_result()
        llm_scores = _make_full_llm_scores(
            {
                "faithfulness": 5,
                "relevance": 5,
                "completeness": 5,
                "safety": 5,
                "communication": 5,
            }
        )

        result = self.aggregator.aggregate(
            code_result=code_result,
            llm_scores=llm_scores,
            intent="general",
        )

        assert result.grade == "S"
        assert result.continuous_score >= 90.0

    def test_grade_c_for_low_scores(self) -> None:
        """모든 축 1점 -> C등급 (< 55)."""
        code_result = _make_code_result()
        llm_scores = _make_full_llm_scores(
            {
                "faithfulness": 1,
                "relevance": 1,
                "completeness": 1,
                "safety": 1,
                "communication": 1,
            }
        )

        result = self.aggregator.aggregate(
            code_result=code_result,
            llm_scores=llm_scores,
            intent="general",
        )

        assert result.grade == "C"
        assert result.continuous_score < 55.0

    def test_eval_result_has_all_fields(self) -> None:
        """EvalResult에 필수 필드가 모두 존재하는지 확인."""
        code_result = _make_code_result()
        llm_scores = _make_full_llm_scores()

        result = self.aggregator.aggregate(
            code_result=code_result,
            llm_scores=llm_scores,
            intent="general",
            model_version="test-model",
            prompt_version="test-prompt",
            eval_duration_ms=200,
            eval_cost_usd=0.05,
        )

        assert hasattr(result, "continuous_score")
        assert hasattr(result, "axis_scores")
        assert hasattr(result, "grade")
        assert hasattr(result, "information_loss")
        assert hasattr(result, "grade_confidence")
        assert hasattr(result, "code_grader_result")
        assert hasattr(result, "llm_grader_result")
        assert hasattr(result, "calibration_status")
        assert hasattr(result, "model_version")
        assert hasattr(result, "prompt_version")
        assert hasattr(result, "eval_duration_ms")
        assert hasattr(result, "eval_cost_usd")
        assert hasattr(result, "metadata")

        assert result.eval_cost_usd == 0.05
        assert result.calibration_status is None
