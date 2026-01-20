"""Answer Node 단위 테스트.

P2: Multi-Intent Policy 조합 주입
"""

from __future__ import annotations

import pytest

from chat_worker.infrastructure.orchestration.langgraph.nodes.answer_node import (
    create_answer_node,
)


class MockAIMessageChunk:
    """테스트용 Mock AIMessageChunk."""

    def __init__(self, content: str):
        self.content = content


class MockLangChainLLM:
    """테스트용 Mock LangChain LLM."""

    def __init__(self, mock_client: "MockLLMClient"):
        self._mock_client = mock_client

    async def astream(self, messages):
        """Mock astream - LangGraph stream_mode="messages" 지원."""
        self._mock_client.call_count += 1
        response = (
            self._mock_client.responses[0] if self._mock_client.responses else "Test response"
        )
        for char in response:
            yield MockAIMessageChunk(content=char)


class MockLLMClient:
    """테스트용 Mock LLM Client."""

    def __init__(self):
        self.responses: list[str] = []
        self.call_count = 0
        self._mock_langchain_llm = MockLangChainLLM(self)

    def set_responses(self, responses: list[str]):
        self.responses = responses

    def get_langchain_llm(self):
        """LangChain LLM 반환 (stream_mode="messages" 지원)."""
        return self._mock_langchain_llm

    async def generate_stream(self, prompt: str, system_prompt: str = ""):
        self.call_count += 1
        response = self.responses[0] if self.responses else "Test response"
        for char in response:
            yield char


class TestAnswerNodeBasic:
    """Answer Node 기본 동작 테스트."""

    @pytest.fixture
    def mock_llm(self) -> MockLLMClient:
        return MockLLMClient()

    @pytest.mark.asyncio
    async def test_basic_answer_generation(self, mock_llm: MockLLMClient):
        """기본 답변 생성 테스트.

        Note: 네이티브 스트리밍 전환으로 event_publisher가 제거됨.
        토큰 스트리밍은 ProcessChatCommand의 astream_events에서 처리.
        """
        mock_llm.set_responses(["안녕하세요!"])

        node = create_answer_node(mock_llm)

        state = {
            "job_id": "test-job-1",
            "message": "안녕",
            "intent": "general",
        }

        result = await node(state)

        assert result["answer"] == "안녕하세요!"
        assert mock_llm.call_count == 1


class TestMultiIntentAnswer:
    """P2: Multi-Intent Policy 조합 주입 테스트."""

    @pytest.fixture
    def mock_llm(self) -> MockLLMClient:
        return MockLLMClient()

    @pytest.mark.asyncio
    async def test_single_intent_uses_single_prompt(self, mock_llm: MockLLMClient):
        """단일 Intent는 일반 프롬프트 사용."""
        mock_llm.set_responses(["답변"])

        node = create_answer_node(mock_llm)

        state = {
            "job_id": "test-job",
            "message": "페트병 버려",
            "intent": "waste",
            "has_multi_intent": False,
            "additional_intents": [],
        }

        await node(state)

        # LLM 호출됨
        assert mock_llm.call_count == 1

    @pytest.mark.asyncio
    async def test_multi_intent_uses_combined_prompt(self, mock_llm: MockLLMClient):
        """Multi-Intent는 조합 프롬프트 사용."""
        mock_llm.set_responses(["복합 답변"])

        node = create_answer_node(mock_llm)

        state = {
            "job_id": "test-job",
            "message": "페트병 버리고 캐릭터 알려줘",
            "intent": "waste",
            "has_multi_intent": True,
            "additional_intents": ["character"],
        }

        result = await node(state)

        assert result["answer"] == "복합 답변"
        assert mock_llm.call_count == 1

    @pytest.mark.asyncio
    async def test_multi_intent_without_additional_uses_single(self, mock_llm: MockLLMClient):
        """has_multi_intent=True지만 additional_intents 없으면 단일 프롬프트."""
        mock_llm.set_responses(["답변"])

        node = create_answer_node(mock_llm)

        state = {
            "job_id": "test-job",
            "message": "테스트",
            "intent": "general",
            "has_multi_intent": True,  # True지만
            "additional_intents": [],  # 추가 Intent 없음
        }

        await node(state)

        # 단일 프롬프트로 처리됨
        assert mock_llm.call_count == 1


class TestAnswerNodeErrorHandling:
    """Answer Node 에러 처리 테스트."""

    @pytest.mark.asyncio
    async def test_llm_error_returns_fallback(self):
        """LLM 오류 시 fallback 메시지 반환.

        Note: 네이티브 스트리밍 전환으로 event_publisher가 제거됨.
        에러 처리는 ProcessChatCommand 레벨에서 담당.
        Node는 fallback 메시지만 반환.
        """

        class ErrorLangChainLLM:
            async def astream(self, messages):
                raise Exception("LLM Error")
                yield  # Generator로 만들기 위해

        class ErrorLLM:
            def __init__(self):
                self._error_llm = ErrorLangChainLLM()

            def get_langchain_llm(self):
                return self._error_llm

            async def generate_stream(self, prompt: str, system_prompt: str = ""):
                raise Exception("LLM Error")
                yield  # Generator로 만들기 위해

        node = create_answer_node(ErrorLLM())

        state = {
            "job_id": "test-job",
            "message": "테스트",
            "intent": "general",
        }

        result = await node(state)

        # fallback 메시지 반환 확인
        assert "오류가 발생했습니다" in result["answer"]
