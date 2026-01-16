"""EvaluateFeedbackCommand 단위 테스트.

CQRS Command(UseCase) 테스트:
- 정책/흐름 테스트
- Port 조립 검증
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from chat_worker.application.commands.evaluate_feedback_command import (
    EvaluateFeedbackCommand,
    EvaluateFeedbackInput,
    EvaluateFeedbackOutput,
)
from chat_worker.application.dto.feedback_result import FeedbackResult
from chat_worker.application.dto.fallback_result import FallbackResult
from chat_worker.domain.enums import FeedbackQuality, FallbackReason


@pytest.fixture
def mock_fallback_orchestrator():
    """Mock FallbackOrchestrator."""
    orchestrator = MagicMock()
    orchestrator.execute_fallback = AsyncMock(
        return_value=FallbackResult.web_search_fallback(
            search_results={"query": "test", "results": []},
            reason=FallbackReason.RAG_LOW_QUALITY,
        )
    )
    return orchestrator


@pytest.fixture
def mock_llm_evaluator():
    """Mock LLM 평가기."""
    evaluator = MagicMock()
    evaluator.evaluate = AsyncMock(
        return_value=FeedbackResult.excellent(score=0.95)
    )
    return evaluator


@pytest.fixture
def mock_web_search():
    """Mock 웹 검색 클라이언트."""
    return MagicMock()


@pytest.fixture
def sample_input() -> EvaluateFeedbackInput:
    """샘플 입력 DTO."""
    return EvaluateFeedbackInput(
        job_id="test-job-123",
        query="플라스틱 분리수거 방법",
        intent="waste",
        rag_results={
            "material": "플라스틱",
            "disposal_method": "깨끗이 씻어서 재활용",
        },
    )


class TestEvaluateFeedbackCommand:
    """EvaluateFeedbackCommand 테스트."""

    def test_execute_returns_output_dto(
        self,
        mock_fallback_orchestrator,
        sample_input,
    ):
        """Command 실행 시 출력 DTO 반환."""
        command = EvaluateFeedbackCommand(
            fallback_orchestrator=mock_fallback_orchestrator,
        )

        output = asyncio.get_event_loop().run_until_complete(
            command.execute(sample_input)
        )

        assert isinstance(output, EvaluateFeedbackOutput)
        assert output.feedback is not None
        assert "rule_evaluation_completed" in output.events

    def test_execute_with_good_rag_results_no_fallback(
        self,
        mock_fallback_orchestrator,
    ):
        """좋은 RAG 결과 시 Fallback 없음."""
        input_dto = EvaluateFeedbackInput(
            job_id="test-job",
            query="플라스틱 분리수거",
            intent="waste",
            rag_results={
                "data": {
                    "material": "플라스틱",
                    "disposal_info": "깨끗이 씻어서 재활용",
                },
                "category": "플라스틱류",
                "플라스틱": True,  # keyword match
                "분리수거": True,  # keyword match
            },
        )

        command = EvaluateFeedbackCommand(
            fallback_orchestrator=mock_fallback_orchestrator,
        )

        output = asyncio.get_event_loop().run_until_complete(
            command.execute(input_dto)
        )

        assert output.fallback_executed is False
        assert output.fallback_result is None
        mock_fallback_orchestrator.execute_fallback.assert_not_called()

    def test_execute_with_no_rag_results_triggers_fallback(
        self,
        mock_fallback_orchestrator,
    ):
        """RAG 결과 없을 시 Fallback 실행."""
        input_dto = EvaluateFeedbackInput(
            job_id="test-job",
            query="특이한 물건 분리수거",
            intent="waste",
            rag_results=None,
        )

        command = EvaluateFeedbackCommand(
            fallback_orchestrator=mock_fallback_orchestrator,
        )

        output = asyncio.get_event_loop().run_until_complete(
            command.execute(input_dto)
        )

        assert output.fallback_executed is True
        assert output.fallback_result is not None
        assert "fallback_started" in output.events
        mock_fallback_orchestrator.execute_fallback.assert_called_once()

    def test_execute_with_llm_evaluator_improves_score(
        self,
        mock_fallback_orchestrator,
        mock_llm_evaluator,
    ):
        """LLM 평가기가 점수를 개선하는 경우."""
        # 낮은 품질의 RAG 결과 (PARTIAL 범위)
        input_dto = EvaluateFeedbackInput(
            job_id="test-job",
            query="플라스틱 분리수거",
            intent="waste",
            rag_results={"data": {"material": "플라스틱"}},  # 부분 결과
        )

        command = EvaluateFeedbackCommand(
            fallback_orchestrator=mock_fallback_orchestrator,
            llm_evaluator=mock_llm_evaluator,
        )

        output = asyncio.get_event_loop().run_until_complete(
            command.execute(input_dto)
        )

        # LLM 평가가 호출됨
        mock_llm_evaluator.evaluate.assert_called_once()
        assert "llm_evaluation_improved" in output.events

    def test_execute_llm_evaluation_failure_graceful(
        self,
        mock_fallback_orchestrator,
        mock_llm_evaluator,
    ):
        """LLM 평가 실패 시 Rule 결과 유지."""
        mock_llm_evaluator.evaluate.side_effect = Exception("LLM Error")

        input_dto = EvaluateFeedbackInput(
            job_id="test-job",
            query="플라스틱 분리수거",
            intent="waste",
            rag_results={"data": {"material": "플라스틱"}},
        )

        command = EvaluateFeedbackCommand(
            fallback_orchestrator=mock_fallback_orchestrator,
            llm_evaluator=mock_llm_evaluator,
        )

        output = asyncio.get_event_loop().run_until_complete(
            command.execute(input_dto)
        )

        assert "llm_evaluation_failed" in output.events
        # 에러가 발생해도 결과는 반환됨
        assert output.feedback is not None


class TestEvaluateFeedbackInput:
    """입력 DTO 테스트."""

    def test_input_is_frozen(self):
        """입력 DTO는 불변."""
        input_dto = EvaluateFeedbackInput(
            job_id="test",
            query="query",
            intent="waste",
            rag_results=None,
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            input_dto.job_id = "changed"


class TestEvaluateFeedbackOutput:
    """출력 DTO 테스트."""

    def test_needs_fallback_property(self):
        """needs_fallback 프로퍼티 테스트."""
        output = EvaluateFeedbackOutput(
            feedback=FeedbackResult.excellent(),
            fallback_executed=True,
        )
        assert output.needs_fallback is True

        output2 = EvaluateFeedbackOutput(
            feedback=FeedbackResult.excellent(),
            fallback_executed=False,
        )
        assert output2.needs_fallback is False

    def test_final_quality_score_property(self):
        """final_quality_score 프로퍼티 테스트."""
        feedback = FeedbackResult.from_score(0.85)
        output = EvaluateFeedbackOutput(feedback=feedback)
        assert output.final_quality_score == 0.85
