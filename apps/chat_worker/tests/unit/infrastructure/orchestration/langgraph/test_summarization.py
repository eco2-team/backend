"""Summarization 단위 테스트.

summarize_messages의 입력 크기 제한 검증.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from chat_worker.infrastructure.orchestration.langgraph.summarization import (
    summarize_messages,
)


class MockLLM:
    """테스트용 LLM mock."""

    def __init__(self, response: str = "요약 결과"):
        self._response = response
        self.last_prompt: str | None = None

    async def generate(self, prompt: str, **kwargs) -> str:
        self.last_prompt = prompt
        return self._response


class TestSummarizeMessagesTruncation:
    """summarize_messages 입력 크기 제한 테스트."""

    @pytest.mark.anyio
    async def test_large_input_truncated(self):
        """800K chars 초과 메시지는 잘림 (tail 보존)."""
        llm = MockLLM()
        # 각 메시지가 100K chars → 10개 = 1M chars (800K 초과)
        messages = [HumanMessage(content="X" * 100_000) for _ in range(10)]

        result = await summarize_messages(
            messages=messages,
            llm=llm,
            max_input_chars=800_000,
        )

        assert result == "요약 결과"
        # 프롬프트에 포함된 messages_text가 800K 이하여야 함
        assert llm.last_prompt is not None
        assert len(llm.last_prompt) <= 900_000  # template overhead 포함

    @pytest.mark.anyio
    async def test_small_input_not_truncated(self):
        """800K chars 이하 메시지는 그대로."""
        llm = MockLLM()
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there"),
        ]

        result = await summarize_messages(
            messages=messages,
            llm=llm,
            max_input_chars=800_000,
        )

        assert result == "요약 결과"
        assert llm.last_prompt is not None
        # 원본 content가 프롬프트에 포함되어야 함
        assert "Hello" in llm.last_prompt
        assert "Hi there" in llm.last_prompt

    @pytest.mark.anyio
    async def test_truncation_preserves_tail(self):
        """잘림 시 최근 메시지(tail)가 보존됨."""
        llm = MockLLM()
        messages = [
            HumanMessage(content="OLD_" + "A" * 500_000),  # 오래된 큰 메시지
            AIMessage(content="RECENT_MESSAGE_PRESERVED"),  # 최근 작은 메시지
        ]

        result = await summarize_messages(
            messages=messages,
            llm=llm,
            max_input_chars=1_000,  # 매우 작은 제한
        )

        assert result == "요약 결과"
        assert llm.last_prompt is not None
        # 최근 메시지(tail)는 보존됨
        assert "RECENT_MESSAGE_PRESERVED" in llm.last_prompt

    @pytest.mark.anyio
    async def test_empty_messages_returns_existing_summary(self):
        """빈 메시지 리스트는 기존 요약 반환."""
        llm = MockLLM()
        result = await summarize_messages(
            messages=[],
            llm=llm,
            existing_summary="이전 요약",
        )
        assert result == "이전 요약"

    @pytest.mark.anyio
    async def test_llm_failure_returns_existing_summary(self):
        """LLM 실패 시 기존 요약 반환."""
        llm = MockLLM()
        llm.generate = AsyncMock(side_effect=RuntimeError("LLM error"))

        result = await summarize_messages(
            messages=[HumanMessage(content="test")],
            llm=llm,
            existing_summary="fallback 요약",
        )
        assert result == "fallback 요약"
