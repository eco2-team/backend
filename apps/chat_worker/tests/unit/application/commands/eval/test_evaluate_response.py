"""EvaluateResponseCommand Unit Tests."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from chat_worker.application.commands.evaluate_response_command import (
    EvaluateResponseCommand,
    EvaluateResponseInput,
)
from chat_worker.application.dto.eval_config import EvalConfig
from chat_worker.application.dto.eval_result import EvalResult
from chat_worker.application.services.eval.code_grader import CodeGraderResult

# ── 테스트 헬퍼 ──────────────────────────────────────────────────────────────


def _make_input(**overrides) -> EvaluateResponseInput:
    """기본 EvaluateResponseInput 팩토리."""
    defaults = {
        "query": "페트병 분리배출 방법은?",
        "intent": "waste",
        "answer": "페트병은 내용물을 비우고 라벨을 제거한 뒤 배출합니다.",
        "rag_context": "환경부 분리배출 가이드",
        "feedback_result": None,
        "job_id": "test-job-001",
    }
    defaults.update(overrides)
    return EvaluateResponseInput(**defaults)


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


def _make_eval_result(grade: str = "A", continuous_score: float = 80.0) -> EvalResult:
    """테스트용 EvalResult 팩토리."""
    return EvalResult(
        continuous_score=continuous_score,
        axis_scores={},
        grade=grade,
        information_loss=9.61,
        grade_confidence=5.0,
        code_grader_result=None,
        llm_grader_result=None,
        calibration_status=None,
        model_version="test-model",
        prompt_version="test-prompt",
        eval_duration_ms=100,
        eval_cost_usd=0.01,
    )


def _make_command(
    code_grader: MagicMock | None = None,
    llm_grader: AsyncMock | None = None,
    score_aggregator: MagicMock | None = None,
    calibration_monitor: AsyncMock | None = None,
    eval_result_gw: AsyncMock | None = None,
    eval_config: EvalConfig | None = None,
) -> EvaluateResponseCommand:
    """EvaluateResponseCommand 팩토리."""
    _code_grader = code_grader or MagicMock()
    if code_grader is None:
        _code_grader.evaluate.return_value = _make_code_result()

    _score_aggregator = score_aggregator or MagicMock()
    if score_aggregator is None:
        _score_aggregator.aggregate.return_value = _make_eval_result()

    config = eval_config or EvalConfig(
        eval_llm_grader_enabled=True,
        eval_regeneration_enabled=False,
        eval_model="gpt-4o-mini",
    )

    return EvaluateResponseCommand(
        code_grader=_code_grader,
        llm_grader=llm_grader,
        score_aggregator=_score_aggregator,
        calibration_monitor=calibration_monitor,
        eval_result_gw=eval_result_gw,
        eval_config=config,
    )


@pytest.mark.eval_unit
class TestEvaluateResponseCommand:
    """EvaluateResponseCommand 3-Tier 평가 오케스트레이터 테스트."""

    async def test_execute_full_pipeline(self) -> None:
        """L1+L2+L3 모두 성공하는 전체 파이프라인."""
        llm_grader = AsyncMock()
        llm_grader.evaluate.return_value = {"faithfulness": MagicMock(score=4, reasoning="good")}

        calibration_monitor = AsyncMock()
        calibration_monitor.check_drift.return_value = {"status": "STABLE"}

        eval_result_gw = AsyncMock()

        config = EvalConfig(
            eval_llm_grader_enabled=True,
            eval_regeneration_enabled=False,
            eval_model="gpt-4o-mini",
            eval_cusum_check_interval=1,
        )

        command = _make_command(
            llm_grader=llm_grader,
            calibration_monitor=calibration_monitor,
            eval_result_gw=eval_result_gw,
            eval_config=config,
        )

        output = await command.execute(_make_input())

        assert output.eval_result is not None
        assert output.calibration_status == "STABLE"
        assert output.needs_regeneration is False

        # L2 LLM Grader 호출 확인
        llm_grader.evaluate.assert_called_once()
        # L3 Calibration Monitor 호출 확인
        calibration_monitor.check_drift.assert_called_once()
        # 결과 저장 확인
        eval_result_gw.save_result.assert_called_once()

    async def test_execute_code_only(self) -> None:
        """llm_grader=None: L1만 실행."""
        command = _make_command(llm_grader=None)

        output = await command.execute(_make_input())

        assert output.eval_result is not None
        assert output.needs_regeneration is False

    async def test_execute_llm_disabled(self) -> None:
        """eval_llm_grader_enabled=False: LLM Grader 스킵."""
        llm_grader = AsyncMock()

        config = EvalConfig(
            eval_llm_grader_enabled=False,
            eval_regeneration_enabled=False,
        )
        command = _make_command(llm_grader=llm_grader, eval_config=config)

        output = await command.execute(_make_input())

        # LLM Grader가 호출되지 않아야 함
        llm_grader.evaluate.assert_not_called()
        assert output.eval_result is not None

    async def test_c_grade_triggers_regeneration(self) -> None:
        """C등급 + eval_regeneration_enabled=True -> needs_regeneration=True."""
        score_aggregator = MagicMock()
        score_aggregator.aggregate.return_value = _make_eval_result(
            grade="C", continuous_score=40.0
        )

        config = EvalConfig(
            eval_llm_grader_enabled=True,
            eval_regeneration_enabled=True,
        )

        llm_grader = AsyncMock()
        llm_grader.evaluate.return_value = {}

        command = _make_command(
            llm_grader=llm_grader,
            score_aggregator=score_aggregator,
            eval_config=config,
        )

        output = await command.execute(_make_input())

        assert output.needs_regeneration is True
        assert output.eval_result.grade == "C"

    async def test_c_grade_no_regeneration_when_disabled(self) -> None:
        """C등급이지만 eval_regeneration_enabled=False -> needs_regeneration=False."""
        score_aggregator = MagicMock()
        score_aggregator.aggregate.return_value = _make_eval_result(
            grade="C", continuous_score=40.0
        )

        config = EvalConfig(
            eval_llm_grader_enabled=False,
            eval_regeneration_enabled=False,
        )

        command = _make_command(
            score_aggregator=score_aggregator,
            eval_config=config,
        )

        output = await command.execute(_make_input())

        assert output.needs_regeneration is False
        assert output.eval_result.grade == "C"

    async def test_improvement_hints_from_failed_slices(self) -> None:
        """L1 실패 슬라이스가 improvement_hints에 포함."""
        code_grader = MagicMock()
        code_result = CodeGraderResult(
            scores={
                "format_compliance": 0.3,
                "length_check": 1.0,
                "language_consistency": 1.0,
                "hallucination_keywords": 0.4,
                "citation_presence": 0.0,
                "intent_answer_alignment": 1.0,
            },
            passed={
                "format_compliance": False,
                "length_check": True,
                "language_consistency": True,
                "hallucination_keywords": False,
                "citation_presence": False,
                "intent_answer_alignment": True,
            },
            details={
                "format_compliance": "미완성 문장",
                "length_check": "적정 길이",
                "language_consistency": "한국어 비율 양호",
                "hallucination_keywords": "금지 표현 2건",
                "citation_presence": "출처 없음",
                "intent_answer_alignment": "구조 양호",
            },
            overall_score=0.55,
        )
        code_grader.evaluate.return_value = code_result

        config = EvalConfig(eval_llm_grader_enabled=False)
        command = _make_command(code_grader=code_grader, eval_config=config)

        output = await command.execute(_make_input())

        # 3개 실패 슬라이스 힌트
        assert len(output.improvement_hints) == 3
        assert any("[L1] format_compliance" in h for h in output.improvement_hints)
        assert any("[L1] hallucination_keywords" in h for h in output.improvement_hints)
        assert any("[L1] citation_presence" in h for h in output.improvement_hints)

    async def test_save_result_called(self) -> None:
        """eval_result_gw가 있으면 save_result 호출."""
        eval_result_gw = AsyncMock()

        config = EvalConfig(eval_llm_grader_enabled=False)
        command = _make_command(eval_result_gw=eval_result_gw, eval_config=config)

        await command.execute(_make_input())

        eval_result_gw.save_result.assert_called_once()

    async def test_save_failure_non_blocking(self) -> None:
        """save_result 실패해도 예외 전파 없이 정상 반환 (non-blocking)."""
        eval_result_gw = AsyncMock()
        eval_result_gw.save_result.side_effect = RuntimeError("DB 연결 실패")

        config = EvalConfig(eval_llm_grader_enabled=False)
        command = _make_command(eval_result_gw=eval_result_gw, eval_config=config)

        # 예외 없이 정상 반환되어야 함
        output = await command.execute(_make_input())

        assert output.eval_result is not None
        eval_result_gw.save_result.assert_called_once()
