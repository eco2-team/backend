"""Web Search Node 단위 테스트.

테스트 케이스:
1. Standalone mode (intent=web_search): 무조건 검색 수행
2. Enrichment mode - 검색 필요: Function Calling으로 needs_search=true
3. Enrichment mode - 검색 불필요: Function Calling으로 needs_search=false
4. 검색 실패 시 FAIL_OPEN: error context 반환, 파이프라인 계속
5. Enrichment mode에서 Function Calling 실패: 빈 dict 반환 (skip)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

pytest.importorskip("langgraph", reason="langgraph not installed")

from chat_worker.infrastructure.orchestration.langgraph.nodes.node_executor import (  # noqa: E402
    NodeExecutor,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.web_search_node import (  # noqa: E402
    create_web_search_node,
)


class MockLLMClient:
    """테스트용 Mock LLM Client (Function Calling + Web Search Tool 지원)."""

    def __init__(self):
        self.function_call_responses: list[tuple[str | None, dict[str, Any] | None]] = []
        self.web_search_responses: list[str] = []
        self.function_call_count = 0
        self.web_search_count = 0
        self.raise_on_function_call = False
        self.raise_on_web_search = False

    def set_function_call_response(
        self,
        function_name: str | None,
        arguments: dict[str, Any] | None,
    ):
        """Function call 응답 설정."""
        self.function_call_responses.append((function_name, arguments))

    def set_web_search_response(self, response: str):
        """Web search 응답 설정."""
        self.web_search_responses.append(response)

    async def generate_function_call(
        self,
        prompt: str,
        functions: list[dict[str, Any]],
        system_prompt: str | None = None,
        function_call: str | dict[str, str] = "auto",
    ) -> tuple[str | None, dict[str, Any] | None]:
        """Function Calling 시뮬레이션."""
        self.function_call_count += 1
        if self.raise_on_function_call:
            raise RuntimeError("Function call failed")
        if self.function_call_responses:
            return self.function_call_responses.pop(0)
        return (None, None)

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[str],
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ):
        """Web Search Tool 시뮬레이션."""
        self.web_search_count += 1
        if self.raise_on_web_search:
            raise RuntimeError("Web search API failed")
        if self.web_search_responses:
            response = self.web_search_responses.pop(0)
            for chunk in [response[i : i + 10] for i in range(0, len(response), 10)]:
                yield chunk
        else:
            yield "검색 결과 없음"


class MockEventPublisher:
    """테스트용 Mock Event Publisher."""

    def __init__(self):
        self.stages: list[dict] = []

    async def notify_stage(
        self,
        task_id: str,
        stage: str,
        status: str,
        progress: int | None = None,
        result: dict[str, Any] | None = None,
        message: str | None = None,
    ):
        self.stages.append(
            {
                "task_id": task_id,
                "stage": stage,
                "status": status,
                "progress": progress,
                "result": result,
                "message": message,
            }
        )
        return "event-id"


class MockCircuitBreaker:
    """테스트용 Mock Circuit Breaker."""

    def __init__(self):
        self.state = MagicMock()
        self.state.value = "closed"

    async def allow_request(self) -> bool:
        return True

    async def record_success(self):
        pass

    async def record_failure(self):
        pass

    def retry_after(self) -> int:
        return 0


class MockCircuitBreakerRegistry:
    """테스트용 Mock Circuit Breaker Registry."""

    def __init__(self):
        self._cb = MockCircuitBreaker()

    def get(self, name: str, threshold: int = 5):
        return self._cb


@pytest.fixture
def mock_llm():
    """Mock LLM Client."""
    return MockLLMClient()


@pytest.fixture
def mock_publisher():
    """Mock Event Publisher."""
    return MockEventPublisher()


@pytest.fixture
def mock_cb_registry():
    """Mock Circuit Breaker Registry."""
    return MockCircuitBreakerRegistry()


@pytest.fixture(autouse=True)
def setup_node_executor(mock_cb_registry):
    """NodeExecutor에 Mock Circuit Breaker 주입."""
    NodeExecutor.reset_instance()
    NodeExecutor.get_instance(cb_registry=mock_cb_registry)
    yield
    NodeExecutor.reset_instance()


class TestWebSearchNodeStandalone:
    """Standalone mode 테스트 (intent=web_search)."""

    @pytest.mark.anyio
    async def test_standalone_executes_search_directly(
        self,
        mock_llm: MockLLMClient,
        mock_publisher: MockEventPublisher,
    ):
        """Standalone mode: Function Calling 없이 바로 검색 수행."""
        mock_llm.set_web_search_response("2026년 분리배출 정책이 변경되었습니다.")

        node = create_web_search_node(llm=mock_llm, event_publisher=mock_publisher)

        state = {
            "job_id": "test-job-1",
            "message": "최신 분리배출 정책 알려줘",
            "intent": "web_search",
        }

        result = await node(state)

        # Function Calling 호출 안됨
        assert mock_llm.function_call_count == 0
        # Web search 호출됨
        assert mock_llm.web_search_count == 1
        # 결과 반환됨
        assert "web_search_results" in result
        ctx = result["web_search_results"]
        assert ctx.get("success") is True
        assert "2026년 분리배출 정책" in ctx["context"]

    @pytest.mark.anyio
    async def test_standalone_search_failure(
        self,
        mock_llm: MockLLMClient,
        mock_publisher: MockEventPublisher,
    ):
        """Standalone mode: 검색 실패 시 error context 반환."""
        mock_llm.raise_on_web_search = True

        node = create_web_search_node(llm=mock_llm, event_publisher=mock_publisher)

        state = {
            "job_id": "test-job-2",
            "message": "환경부 뉴스",
            "intent": "web_search",
        }

        result = await node(state)

        # FAIL_OPEN: error context 반환
        assert "web_search_results" in result
        ctx = result["web_search_results"]
        assert ctx.get("success") is False

    @pytest.mark.anyio
    async def test_standalone_empty_result(
        self,
        mock_llm: MockLLMClient,
        mock_publisher: MockEventPublisher,
    ):
        """Standalone mode: 빈 결과 시 error context."""
        mock_llm.set_web_search_response("")  # 빈 응답

        node = create_web_search_node(llm=mock_llm, event_publisher=mock_publisher)

        state = {
            "job_id": "test-job-3",
            "message": "2026 재활용 규제",
            "intent": "web_search",
        }

        result = await node(state)

        assert "web_search_results" in result
        ctx = result["web_search_results"]
        assert ctx.get("success") is False


class TestWebSearchNodeEnrichment:
    """Enrichment mode 테스트 (다른 intent의 보조)."""

    @pytest.mark.anyio
    async def test_enrichment_search_needed(
        self,
        mock_llm: MockLLMClient,
        mock_publisher: MockEventPublisher,
    ):
        """Enrichment mode: Function Calling이 검색 필요하다고 판단."""
        mock_llm.set_function_call_response(
            "web_search_decision",
            {"needs_search": True, "search_query": "2026 페트병 규제 변경사항"},
        )
        mock_llm.set_web_search_response("페트병 재활용 규제가 2026년에 강화됩니다.")

        node = create_web_search_node(llm=mock_llm, event_publisher=mock_publisher)

        state = {
            "job_id": "test-job-4",
            "message": "올해 페트병 규제 바뀐거 있어?",
            "intent": "waste",  # 주 intent는 waste
        }

        result = await node(state)

        # Function Calling 호출됨
        assert mock_llm.function_call_count == 1
        # Web search 호출됨 (최적화된 쿼리로)
        assert mock_llm.web_search_count == 1
        # 결과 반환됨
        assert "web_search_results" in result
        ctx = result["web_search_results"]
        assert ctx.get("success") is True
        assert "페트병 재활용 규제" in ctx["context"]

    @pytest.mark.anyio
    async def test_enrichment_search_not_needed(
        self,
        mock_llm: MockLLMClient,
        mock_publisher: MockEventPublisher,
    ):
        """Enrichment mode: Function Calling이 검색 불필요하다고 판단."""
        mock_llm.set_function_call_response(
            "web_search_decision",
            {"needs_search": False},
        )

        node = create_web_search_node(llm=mock_llm, event_publisher=mock_publisher)

        state = {
            "job_id": "test-job-5",
            "message": "페트병 분리배출 방법",
            "intent": "waste",
        }

        result = await node(state)

        # Function Calling 호출됨
        assert mock_llm.function_call_count == 1
        # Web search 호출 안됨
        assert mock_llm.web_search_count == 0
        # web_search_results 없음 (skip)
        assert "web_search_results" not in result

    @pytest.mark.anyio
    async def test_enrichment_function_call_failure(
        self,
        mock_llm: MockLLMClient,
        mock_publisher: MockEventPublisher,
    ):
        """Enrichment mode: Function Calling 실패 시 skip."""
        mock_llm.raise_on_function_call = True

        node = create_web_search_node(llm=mock_llm, event_publisher=mock_publisher)

        state = {
            "job_id": "test-job-6",
            "message": "올해 정책 뭐 바뀌었어?",
            "intent": "waste",
        }

        result = await node(state)

        # Function Calling 실패
        assert mock_llm.function_call_count == 1
        # Web search 호출 안됨
        assert mock_llm.web_search_count == 0
        # web_search_results 없음 (skip)
        assert "web_search_results" not in result

    @pytest.mark.anyio
    async def test_enrichment_no_function_call_response(
        self,
        mock_llm: MockLLMClient,
        mock_publisher: MockEventPublisher,
    ):
        """Enrichment mode: Function Calling 응답이 None이면 skip."""
        # 기본 응답: (None, None)
        node = create_web_search_node(llm=mock_llm, event_publisher=mock_publisher)

        state = {
            "job_id": "test-job-7",
            "message": "일반 분리배출 질문",
            "intent": "waste",
        }

        result = await node(state)

        assert mock_llm.function_call_count == 1
        assert mock_llm.web_search_count == 0
        # web_search_results 없음 (skip)
        assert "web_search_results" not in result


class TestWebSearchNodeEvents:
    """이벤트 발행 테스트."""

    @pytest.mark.anyio
    async def test_progress_events_on_success(
        self,
        mock_llm: MockLLMClient,
        mock_publisher: MockEventPublisher,
    ):
        """성공 시 started + completed 이벤트 발행."""
        mock_llm.set_web_search_response("검색 결과입니다.")

        node = create_web_search_node(llm=mock_llm, event_publisher=mock_publisher)

        state = {
            "job_id": "test-job-8",
            "message": "최신 뉴스",
            "intent": "web_search",
        }

        await node(state)

        started = [e for e in mock_publisher.stages if e["status"] == "started"]
        assert len(started) >= 1
        assert started[0]["stage"] == "web_search"

        completed = [e for e in mock_publisher.stages if e["status"] == "completed"]
        assert len(completed) >= 1
        assert completed[0]["stage"] == "web_search"

    @pytest.mark.anyio
    async def test_progress_events_on_failure(
        self,
        mock_llm: MockLLMClient,
        mock_publisher: MockEventPublisher,
    ):
        """실패 시 started + failed 이벤트 발행."""
        mock_llm.raise_on_web_search = True

        node = create_web_search_node(llm=mock_llm, event_publisher=mock_publisher)

        state = {
            "job_id": "test-job-9",
            "message": "최신 규제",
            "intent": "web_search",
        }

        await node(state)

        started = [e for e in mock_publisher.stages if e["status"] == "started"]
        assert len(started) >= 1

        failed = [e for e in mock_publisher.stages if e["status"] == "failed"]
        assert len(failed) >= 1
        assert failed[0]["stage"] == "web_search"

    @pytest.mark.anyio
    async def test_no_events_without_publisher(
        self,
        mock_llm: MockLLMClient,
    ):
        """event_publisher=None이면 이벤트 발행 안됨 (에러 없이)."""
        mock_llm.set_web_search_response("결과")

        node = create_web_search_node(llm=mock_llm, event_publisher=None)

        state = {
            "job_id": "test-job-10",
            "message": "최신 정책",
            "intent": "web_search",
        }

        result = await node(state)
        assert "web_search_results" in result


class TestWebSearchNodeTruncation:
    """웹 검색 결과 크기 제한 테스트."""

    @pytest.mark.anyio
    async def test_large_result_truncated(
        self,
        mock_llm: MockLLMClient,
        mock_publisher: MockEventPublisher,
    ):
        """50K chars 초과 결과는 잘림."""
        large_response = "A" * 100_000  # 100K chars
        mock_llm.set_web_search_response(large_response)

        node = create_web_search_node(llm=mock_llm, event_publisher=mock_publisher)

        state = {
            "job_id": "test-job-truncate",
            "message": "대량 검색",
            "intent": "web_search",
        }

        result = await node(state)

        assert "web_search_results" in result
        ctx = result["web_search_results"]
        assert ctx.get("success") is True
        # 결과가 50K로 잘려야 함
        assert len(ctx["context"]) <= 50_000

    @pytest.mark.anyio
    async def test_small_result_not_truncated(
        self,
        mock_llm: MockLLMClient,
        mock_publisher: MockEventPublisher,
    ):
        """50K chars 이하 결과는 그대로."""
        normal_response = "B" * 10_000  # 10K chars
        mock_llm.set_web_search_response(normal_response)

        node = create_web_search_node(llm=mock_llm, event_publisher=mock_publisher)

        state = {
            "job_id": "test-job-no-truncate",
            "message": "일반 검색",
            "intent": "web_search",
        }

        result = await node(state)

        assert "web_search_results" in result
        ctx = result["web_search_results"]
        assert ctx.get("success") is True
        assert len(ctx["context"]) == 10_000
