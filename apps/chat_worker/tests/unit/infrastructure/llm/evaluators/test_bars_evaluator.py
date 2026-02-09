"""OpenAIBARSEvaluator Adapter Unit Tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from chat_worker.domain.value_objects.axis_score import AxisScore
from chat_worker.infrastructure.llm.evaluators.bars_evaluator import (
    OpenAIBARSEvaluator,
)
from chat_worker.infrastructure.llm.evaluators.schemas import (
    AxisEvaluation,
    BARSEvalOutput,
    EVAL_AXES,
    SingleAxisEvalOutput,
)


def _make_axis_eval(score: int = 3) -> AxisEvaluation:
    return AxisEvaluation(
        score=score,
        evidence="테스트 근거",
        reasoning="테스트 이유",
    )


def _make_bars_output() -> BARSEvalOutput:
    return BARSEvalOutput(
        faithfulness=_make_axis_eval(4),
        relevance=_make_axis_eval(3),
        completeness=_make_axis_eval(5),
        safety=_make_axis_eval(4),
        communication=_make_axis_eval(3),
    )


def _make_evaluator(llm_mock: AsyncMock) -> OpenAIBARSEvaluator:
    """프롬프트 로딩을 패치하여 Evaluator 생성."""
    with patch(
        "chat_worker.infrastructure.llm.evaluators.bars_evaluator.load_prompt_file",
        return_value="mocked rubric",
    ):
        return OpenAIBARSEvaluator(
            llm_client=llm_mock,
            temperature=0.1,
            max_tokens=1000,
        )


@pytest.mark.eval_unit
class TestEvaluateAllAxes:
    """evaluate_all_axes 메서드 테스트."""

    async def test_returns_all_five_axes(self) -> None:
        """5축 전체 AxisScore dict를 반환한다."""
        llm = AsyncMock()
        llm.generate_structured = AsyncMock(return_value=_make_bars_output())
        evaluator = _make_evaluator(llm)

        result = await evaluator.evaluate_all_axes(
            query="플라스틱 분리배출",
            context="플라스틱은 라벨 제거 후 배출",
            answer="라벨을 제거하세요.",
        )

        assert set(result.keys()) == set(EVAL_AXES)
        for axis, score in result.items():
            assert isinstance(score, AxisScore)
            assert 1 <= score.score <= 5

    async def test_axis_order_shuffled(self) -> None:
        """루브릭 블록의 축 순서가 셔플된다 (위치 편향 완화)."""
        llm = AsyncMock()
        llm.generate_structured = AsyncMock(return_value=_make_bars_output())
        evaluator = _make_evaluator(llm)

        prompts: list[str] = []
        original_generate = llm.generate_structured

        async def capture_prompt(**kwargs):
            prompts.append(kwargs.get("prompt", ""))
            return await original_generate(**kwargs)

        llm.generate_structured = capture_prompt

        # 여러 번 호출하여 최소 한 번은 다른 순서가 나오는지 확인
        # (5!=120 가지이므로 10번이면 거의 확실)
        for _ in range(10):
            await evaluator.evaluate_all_axes(
                query="q",
                context="c",
                answer="a",
            )

        # 프롬프트에서 축 순서 추출
        orders = []
        for p in prompts:
            order = []
            for axis in EVAL_AXES:
                pos = p.find(f"### {axis.upper()}")
                if pos >= 0:
                    order.append((pos, axis))
            order.sort()
            orders.append(tuple(a for _, a in order))

        # 최소 2가지 이상 다른 순서가 존재해야 함
        assert len(set(orders)) >= 2, "축 순서가 셔플되지 않았습니다"

    async def test_llm_called_once(self) -> None:
        """단일 프롬프트로 1회 LLM 호출 (비용 절감)."""
        llm = AsyncMock()
        llm.generate_structured = AsyncMock(return_value=_make_bars_output())
        evaluator = _make_evaluator(llm)

        await evaluator.evaluate_all_axes(query="q", context="c", answer="a")

        assert llm.generate_structured.call_count == 1


@pytest.mark.eval_unit
class TestEvaluateAxis:
    """evaluate_axis 단일 축 평가 테스트."""

    async def test_returns_single_axis_score(self) -> None:
        """단일 축 AxisScore를 반환한다."""
        llm = AsyncMock()
        single_output = SingleAxisEvalOutput(evaluation=_make_axis_eval(5))
        llm.generate_structured = AsyncMock(return_value=single_output)
        evaluator = _make_evaluator(llm)

        result = await evaluator.evaluate_axis(
            axis="faithfulness",
            query="q",
            context="c",
            answer="a",
        )

        assert isinstance(result, AxisScore)
        assert result.axis == "faithfulness"
        assert result.score == 5


@pytest.mark.eval_unit
class TestRetryWithRepair:
    """retry-with-repair 로직 테스트."""

    async def test_retry_on_first_failure(self) -> None:
        """첫 파싱 실패 시 재시도하여 성공한다."""
        llm = AsyncMock()
        llm.generate_structured = AsyncMock(
            side_effect=[
                ValueError("JSON parse error"),
                _make_bars_output(),
            ]
        )
        evaluator = _make_evaluator(llm)

        result = await evaluator.evaluate_all_axes(query="q", context="c", answer="a")

        assert set(result.keys()) == set(EVAL_AXES)
        assert llm.generate_structured.call_count == 2

    async def test_raises_after_max_retries(self) -> None:
        """최대 재시도 후 ValueError를 발생시킨다."""
        llm = AsyncMock()
        llm.generate_structured = AsyncMock(
            side_effect=ValueError("JSON parse error"),
        )
        evaluator = _make_evaluator(llm)

        with pytest.raises(ValueError, match="parse failed after"):
            await evaluator.evaluate_all_axes(query="q", context="c", answer="a")

        # _MAX_PARSE_RETRIES=2 → 총 3회 호출
        assert llm.generate_structured.call_count == 3
