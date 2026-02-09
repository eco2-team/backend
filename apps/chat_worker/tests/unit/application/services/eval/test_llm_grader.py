"""LLMGraderService Unit Tests."""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock

from chat_worker.application.dto.eval_config import EvalConfig
from chat_worker.application.services.eval.llm_grader import LLMGraderService
from chat_worker.domain.value_objects.axis_score import AxisScore

# ── 테스트 상수 ──────────────────────────────────────────────────────────────

_AXES = ["faithfulness", "relevance", "completeness", "safety", "communication"]

_QUERY = "페트병 분리배출 방법은?"
_CONTEXT = "환경부 분리배출 가이드"
_ANSWER = "페트병은 내용물을 비우고 라벨을 제거한 뒤 배출합니다."
_INTENT = "waste"


def _make_axis_score(axis: str, score: int) -> AxisScore:
    """테스트용 AxisScore 팩토리."""
    return AxisScore(
        axis=axis,
        score=score,
        evidence="테스트 근거 텍스트",
        reasoning="테스트 채점 이유",
    )


def _make_all_axes_scores(scores: dict[str, int]) -> dict[str, AxisScore]:
    """5축 전체 AxisScore dict 생성."""
    return {axis: _make_axis_score(axis, s) for axis, s in scores.items()}


def _make_service(
    mock_evaluator: AsyncMock,
    eval_config: EvalConfig | None = None,
) -> LLMGraderService:
    """LLMGraderService 팩토리."""
    config = eval_config or EvalConfig(eval_mode="async", eval_self_consistency_runs=3)
    return LLMGraderService(bars_evaluator=mock_evaluator, eval_config=config)


@pytest.mark.eval_unit
class TestLLMGraderService:
    """LLMGraderService L2 LLM 기반 BARS 5축 평가 테스트."""

    async def test_basic_evaluation_returns_all_axes(self) -> None:
        """안전한 점수(1,3,5)로 모든 5축이 반환되는지 확인."""
        scores = {
            "faithfulness": 5,
            "relevance": 5,
            "completeness": 3,
            "safety": 5,
            "communication": 3,
        }
        mock_evaluator = AsyncMock()
        mock_evaluator.evaluate_all_axes.return_value = _make_all_axes_scores(scores)

        service = _make_service(mock_evaluator)

        result = await service.evaluate(
            query=_QUERY, context=_CONTEXT, answer=_ANSWER, intent=_INTENT
        )

        assert set(result.keys()) == set(_AXES)
        for axis in _AXES:
            assert result[axis].score == scores[axis]

        # Self-Consistency가 트리거되지 않아야 함 (경계점수 2, 4 중 4만 있고 4는 경계)
        # faithfulness=4는 경계이므로 evaluate_axis가 호출됨
        # 하지만 기본 테스트에서는 5축 all_axes 호출 1회 확인
        mock_evaluator.evaluate_all_axes.assert_called_once()

    async def test_self_consistency_triggered_on_boundary(self) -> None:
        """경계 점수(score=2)에서 Self-Consistency 재평가가 트리거되는지 확인."""
        scores = {
            "faithfulness": 2,
            "relevance": 5,
            "completeness": 3,
            "safety": 5,
            "communication": 3,
        }
        mock_evaluator = AsyncMock()
        mock_evaluator.evaluate_all_axes.return_value = _make_all_axes_scores(scores)

        # Self-Consistency 재평가 결과: 매번 score=2 반환 (중앙값 동일 -> 추가 호출 없음)
        mock_evaluator.evaluate_axis.return_value = _make_axis_score("faithfulness", 2)

        config = EvalConfig(eval_mode="async", eval_self_consistency_runs=3)
        service = _make_service(mock_evaluator, config)

        result = await service.evaluate(
            query=_QUERY, context=_CONTEXT, answer=_ANSWER, intent=_INTENT
        )

        # evaluate_all_axes 1회 + evaluate_axis N회 (self_consistency_runs=3)
        mock_evaluator.evaluate_all_axes.assert_called_once()
        # faithfulness가 boundary(2)이므로 evaluate_axis 3회 호출
        # 중앙값 = 2 (원래값과 동일) -> 추가 final_score 호출 없음
        assert mock_evaluator.evaluate_axis.call_count == 3
        assert result["faithfulness"].score == 2

    async def test_self_consistency_not_triggered_on_safe_scores(self) -> None:
        """안전 점수(1, 3, 5)에서는 Self-Consistency 재평가가 발생하지 않음."""
        scores = {
            "faithfulness": 1,
            "relevance": 3,
            "completeness": 5,
            "safety": 1,
            "communication": 3,
        }
        mock_evaluator = AsyncMock()
        mock_evaluator.evaluate_all_axes.return_value = _make_all_axes_scores(scores)

        service = _make_service(mock_evaluator)

        result = await service.evaluate(
            query=_QUERY, context=_CONTEXT, answer=_ANSWER, intent=_INTENT
        )

        # 경계점수(2, 4)가 없으므로 evaluate_axis 호출 없음
        mock_evaluator.evaluate_all_axes.assert_called_once()
        mock_evaluator.evaluate_axis.assert_not_called()
        assert set(result.keys()) == set(_AXES)

    async def test_timeout_returns_empty_dict(self) -> None:
        """타임아웃 시 빈 딕셔너리 반환 (graceful degradation)."""
        mock_evaluator = AsyncMock()

        async def slow_evaluate(*args, **kwargs):
            await asyncio.sleep(100)
            return {}

        mock_evaluator.evaluate_all_axes.side_effect = slow_evaluate

        # sync 모드: 타임아웃 5초
        config = EvalConfig(eval_mode="sync", eval_self_consistency_runs=3)
        service = _make_service(mock_evaluator, config)

        result = await service.evaluate(
            query=_QUERY, context=_CONTEXT, answer=_ANSWER, intent=_INTENT
        )

        assert result == {}

    async def test_exception_returns_empty_dict(self) -> None:
        """예외 발생 시 빈 딕셔너리 반환 (graceful degradation)."""
        mock_evaluator = AsyncMock()
        mock_evaluator.evaluate_all_axes.side_effect = RuntimeError("LLM API 오류")

        service = _make_service(mock_evaluator)

        result = await service.evaluate(
            query=_QUERY, context=_CONTEXT, answer=_ANSWER, intent=_INTENT
        )

        assert result == {}

    async def test_evaluator_called_with_correct_args(self) -> None:
        """evaluate_all_axes가 올바른 인자로 호출되는지 확인."""
        scores = {
            "faithfulness": 3,
            "relevance": 3,
            "completeness": 3,
            "safety": 3,
            "communication": 3,
        }
        mock_evaluator = AsyncMock()
        mock_evaluator.evaluate_all_axes.return_value = _make_all_axes_scores(scores)

        service = _make_service(mock_evaluator)

        await service.evaluate(query=_QUERY, context=_CONTEXT, answer=_ANSWER, intent=_INTENT)

        mock_evaluator.evaluate_all_axes.assert_called_once_with(
            query=_QUERY,
            context=_CONTEXT,
            answer=_ANSWER,
        )
