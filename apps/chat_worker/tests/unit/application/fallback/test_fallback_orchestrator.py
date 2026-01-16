"""Fallback Orchestrator Service Tests.

Fallback 체인 오케스트레이터 테스트.

리팩토링 후:
- FallbackOrchestrator는 순수 비즈니스 로직만 담당
- web_search_client는 execute_fallback 메서드에서 주입
- Port 의존성 제거 (Node에서 조립)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from chat_worker.application.dto.fallback_result import FallbackResult
from chat_worker.application.services.fallback_orchestrator import FallbackOrchestrator
from chat_worker.application.dto.feedback_result import FeedbackResult as FeedbackResultType
from chat_worker.domain.enums import FallbackReason, FeedbackQuality


class TestFallbackResult:
    """FallbackResult DTO 테스트."""

    def test_web_search_fallback_success(self) -> None:
        """웹 검색 Fallback 성공."""
        result = FallbackResult.web_search_fallback(
            {"results": [{"title": "test"}]},
            FallbackReason.RAG_NO_RESULT,
        )
        assert result.success is True
        assert result.strategy_used == "web_search"
        assert result.next_node == "answer"

    def test_web_search_fallback_no_results(self) -> None:
        """웹 검색 Fallback 결과 없음."""
        result = FallbackResult.web_search_fallback(
            {},
            FallbackReason.RAG_NO_RESULT,
        )
        assert result.success is False  # 빈 결과
        assert result.strategy_used == "web_search"

    def test_clarification_fallback(self) -> None:
        """명확화 요청 Fallback."""
        result = FallbackResult.clarification_fallback(
            "무엇이 궁금하신가요?",
            FallbackReason.INTENT_LOW_CONFIDENCE,
        )
        assert result.success is True
        assert result.strategy_used == "clarify"
        assert result.message == "무엇이 궁금하신가요?"

    def test_skip_fallback(self) -> None:
        """Fallback 스킵."""
        result = FallbackResult.skip_fallback(FallbackReason.RAG_NO_RESULT)
        assert result.success is False
        assert result.strategy_used == "skip"
        assert result.next_node == "answer"

    def test_to_state_update(self) -> None:
        """state 업데이트 변환."""
        result = FallbackResult(
            success=True,
            strategy_used="web_search",
            reason=FallbackReason.RAG_NO_RESULT,
            data={"web_search_results": {"query": "test"}},
            message="추가 정보 검색 완료",
        )
        update = result.to_state_update()

        assert update["fallback_used"] is True
        assert update["fallback_strategy"] == "web_search"
        assert update["web_search_results"] == {"query": "test"}
        assert update["fallback_message"] == "추가 정보 검색 완료"


class TestFallbackReason:
    """FallbackReason Enum 테스트."""

    def test_get_fallback_strategy_rag_no_result(self) -> None:
        """RAG 결과 없음 → web_search."""
        assert FallbackReason.RAG_NO_RESULT.get_fallback_strategy() == "web_search"

    def test_get_fallback_strategy_intent_low(self) -> None:
        """Intent 낮음 → clarify."""
        assert FallbackReason.INTENT_LOW_CONFIDENCE.get_fallback_strategy() == "clarify"

    def test_is_retryable_subagent(self) -> None:
        """Subagent 실패는 재시도 가능."""
        assert FallbackReason.SUBAGENT_FAILURE.is_retryable() is True

    def test_is_retryable_rag(self) -> None:
        """RAG 실패는 재시도 불가."""
        assert FallbackReason.RAG_NO_RESULT.is_retryable() is False


class TestFallbackOrchestrator:
    """FallbackOrchestrator 테스트.

    리팩토링 후 서비스는 순수 비즈니스 로직.
    - 생성자에 Port 의존 없음
    - web_search_client는 execute_fallback 호출 시 주입
    """

    @pytest.fixture
    def mock_web_search(self) -> AsyncMock:
        """Mock 웹 검색 클라이언트."""
        mock = AsyncMock()
        mock.search = AsyncMock()
        return mock

    @pytest.fixture
    def orchestrator(self) -> FallbackOrchestrator:
        """Orchestrator 인스턴스 (Port 없이 생성)."""
        return FallbackOrchestrator(max_retries=2)

    @pytest.mark.asyncio
    async def test_execute_web_search_success(
        self,
        orchestrator: FallbackOrchestrator,
        mock_web_search: AsyncMock,
    ) -> None:
        """웹 검색 Fallback 성공."""
        # Mock 응답 설정
        mock_response = MagicMock()
        mock_response.results = [
            MagicMock(title="플라스틱 분리수거", url="http://test.com", snippet="내용")
        ]
        mock_response.query = "플라스틱 분리수거 방법"
        mock_web_search.search.return_value = mock_response

        # web_search_client를 메서드 인자로 전달
        result = await orchestrator.execute_fallback(
            reason=FallbackReason.RAG_NO_RESULT,
            query="플라스틱 분리수거",
            state={"job_id": "test"},
            web_search_client=mock_web_search,  # 메서드 인자로 주입
        )

        assert result.success is True
        assert result.strategy_used == "web_search"
        mock_web_search.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_web_search_no_results(
        self,
        orchestrator: FallbackOrchestrator,
        mock_web_search: AsyncMock,
    ) -> None:
        """웹 검색 Fallback 결과 없음."""
        mock_response = MagicMock()
        mock_response.results = []
        mock_web_search.search.return_value = mock_response

        result = await orchestrator.execute_fallback(
            reason=FallbackReason.RAG_NO_RESULT,
            query="플라스틱 분리수거",
            state={"job_id": "test"},
            web_search_client=mock_web_search,
        )

        # 결과 없으면 skip으로 폴백
        assert result.success is False
        assert result.strategy_used == "skip"

    @pytest.mark.asyncio
    async def test_execute_without_web_search_client(
        self,
        orchestrator: FallbackOrchestrator,
    ) -> None:
        """웹 검색 클라이언트 없으면 skip."""
        result = await orchestrator.execute_fallback(
            reason=FallbackReason.RAG_NO_RESULT,
            query="플라스틱 분리수거",
            state={"job_id": "test"},
            # web_search_client 미제공
        )

        assert result.success is False
        assert result.strategy_used == "skip"

    @pytest.mark.asyncio
    async def test_execute_clarification(
        self,
        orchestrator: FallbackOrchestrator,
    ) -> None:
        """명확화 요청 Fallback."""
        result = await orchestrator.execute_fallback(
            reason=FallbackReason.INTENT_LOW_CONFIDENCE,
            query="이거",
            state={"job_id": "test", "intent": "waste"},
        )

        assert result.success is True
        assert result.strategy_used == "clarify"
        assert result.message is not None
        assert "분리수거" in result.message

    @pytest.mark.asyncio
    async def test_execute_general_llm_fallback(
        self,
        orchestrator: FallbackOrchestrator,
    ) -> None:
        """General LLM Fallback (web_search 다음 전략)."""
        result = await orchestrator.execute_fallback(
            reason=FallbackReason.RAG_NO_RESULT,
            query="플라스틱 분리수거",
            state={"job_id": "test"},
            current_strategy="web_search",  # 이미 web_search 시도 후
        )

        assert result.success is True
        assert result.strategy_used == "general_llm"
        assert result.metadata.get("use_llm_knowledge") is True

    def test_should_fallback_rag_no_result(
        self,
        orchestrator: FallbackOrchestrator,
    ) -> None:
        """RAG 결과 없음 → Fallback 필요."""
        state = {"intent": "waste", "disposal_rules": None}
        needs, reason = orchestrator.should_fallback(state)

        assert needs is True
        assert reason == FallbackReason.RAG_NO_RESULT

    def test_should_fallback_low_confidence(
        self,
        orchestrator: FallbackOrchestrator,
    ) -> None:
        """Intent 신뢰도 낮음 → Fallback 필요."""
        state = {"intent": "general", "intent_confidence": 0.2}
        needs, reason = orchestrator.should_fallback(state)

        assert needs is True
        assert reason == FallbackReason.INTENT_LOW_CONFIDENCE

    def test_should_not_fallback_good_result(
        self,
        orchestrator: FallbackOrchestrator,
    ) -> None:
        """좋은 결과 → Fallback 불필요."""
        state = {
            "intent": "waste",
            "disposal_rules": {"data": {"info": "something"}},
            "intent_confidence": 0.9,
        }
        needs, reason = orchestrator.should_fallback(state)

        assert needs is False
        assert reason is None

    def test_should_fallback_with_feedback(
        self,
        orchestrator: FallbackOrchestrator,
    ) -> None:
        """피드백 기반 Fallback 판단."""
        feedback = FeedbackResultType(
            quality=FeedbackQuality.POOR,
            score=0.25,
            needs_fallback=True,
            fallback_reason=FallbackReason.RAG_LOW_QUALITY,
        )
        state = {"intent": "waste", "disposal_rules": {"data": {}}}
        needs, reason = orchestrator.should_fallback(state, feedback)

        assert needs is True
        assert reason == FallbackReason.RAG_LOW_QUALITY

    def test_should_fallback_subagent_failure(
        self,
        orchestrator: FallbackOrchestrator,
    ) -> None:
        """Subagent 실패 → Fallback 필요."""
        state = {"intent": "character", "subagent_error": "Connection timeout"}
        needs, reason = orchestrator.should_fallback(state)

        assert needs is True
        assert reason == FallbackReason.SUBAGENT_FAILURE

    @pytest.mark.asyncio
    async def test_execute_retry_within_limit(
        self,
        orchestrator: FallbackOrchestrator,
    ) -> None:
        """재시도 횟수 내 재시도."""
        # SUBAGENT_FAILURE의 기본 전략은 "retry"
        result = await orchestrator.execute_fallback(
            reason=FallbackReason.SUBAGENT_FAILURE,
            query="캐릭터 정보",
            state={"job_id": "test", "retry_count": 0},
            # current_strategy=None → 첫 번째 전략 "retry" 선택
        )

        # retry 전략은 should_retry 메타데이터 전달
        assert result.strategy_used == "retry"
        assert result.metadata.get("should_retry") is True

    @pytest.mark.asyncio
    async def test_execute_retry_max_reached(
        self,
        orchestrator: FallbackOrchestrator,
    ) -> None:
        """최대 재시도 횟수 도달 시 skip."""
        # SUBAGENT_FAILURE의 기본 전략은 "retry"
        result = await orchestrator.execute_fallback(
            reason=FallbackReason.SUBAGENT_FAILURE,
            query="캐릭터 정보",
            state={"job_id": "test", "retry_count": 2},  # max_retries=2
            # current_strategy=None → "retry" 선택되지만 max 도달로 skip
        )

        assert result.success is False
        assert result.strategy_used == "skip"
