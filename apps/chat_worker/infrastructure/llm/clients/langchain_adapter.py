"""LangChain LLM Adapter - LLMClientPort를 LangChain Runnable로 구현.

LangGraph stream_mode="messages"가 토큰을 캡처할 수 있도록
LangChain BaseChatModel 기반 LLM을 LLMClientPort 인터페이스로 래핑.

아키텍처:
```
GenerateAnswerCommand
    │
    └── LLMClientPort.generate_stream()  ← 인터페이스
            │
            └── LangChainLLMAdapter  ← 이 파일
                    │
                    └── LangChainOpenAIRunnable.astream()
                            │
                            └── AIMessageChunk yield
                                    │
                                    └── LangGraph stream_mode="messages" 캡처
```

핵심:
- LLMClientPort 인터페이스 구현
- 내부적으로 LangChain Runnable 사용
- astream() 호출로 토큰이 LangGraph 이벤트 시스템에 노출
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from chat_worker.application.ports.llm import LLMClientPort

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LangChainLLMAdapter(LLMClientPort):
    """LangChain Runnable을 LLMClientPort로 래핑.

    기존 GenerateAnswerCommand와 호환되면서
    LangGraph stream_mode="messages"로 토큰 캡처 가능.

    Usage:
        from chat_worker.infrastructure.llm.clients import LangChainOpenAIRunnable

        runnable = LangChainOpenAIRunnable(model="gpt-4o")
        adapter = LangChainLLMAdapter(runnable)

        # GenerateAnswerCommand에서 사용
        async for token in adapter.generate_stream(prompt, system_prompt):
            # LangGraph stream_mode="messages"에서 자동 캡처
            print(token)

        # 직접 LangChain LLM 사용 (stream_mode="messages" 지원)
        langchain_llm = adapter.get_langchain_llm()
        async for chunk in langchain_llm.astream(messages):
            print(chunk.content)
    """

    def __init__(self, llm: "BaseChatModel") -> None:
        """초기화.

        Args:
            llm: LangChain BaseChatModel 인스턴스 (LangChainOpenAIRunnable 등)
        """
        self._llm = llm
        logger.info(
            "LangChainLLMAdapter initialized",
            extra={"llm_type": type(llm).__name__},
        )

    def get_langchain_llm(self) -> "BaseChatModel":
        """내부 LangChain LLM 반환.

        LangGraph stream_mode="messages"를 위해 직접 LLM 접근이 필요할 때 사용.
        answer_node에서 직접 llm.astream(messages)를 호출하면
        LangGraph가 AIMessageChunk를 캡처할 수 있음.

        Returns:
            내부 BaseChatModel 인스턴스
        """
        return self._llm

    def _build_messages(
        self,
        prompt: str,
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[HumanMessage | SystemMessage]:
        """LangChain 메시지 리스트 구성."""
        messages: list[HumanMessage | SystemMessage] = []

        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))

        user_content = prompt
        if context:
            context_str = json.dumps(context, ensure_ascii=False, indent=2)
            user_content = f"## Context\n{context_str}\n\n## Question\n{prompt}"

        messages.append(HumanMessage(content=user_content))
        return messages

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """텍스트 생성 (비스트리밍).

        Args:
            prompt: 사용자 프롬프트
            system_prompt: 시스템 프롬프트
            context: 추가 컨텍스트
            max_tokens: 최대 토큰 수 (무시됨, Runnable 초기화 시 설정)
            temperature: 생성 온도 (무시됨, Runnable 초기화 시 설정)

        Returns:
            생성된 텍스트
        """
        messages = self._build_messages(prompt, system_prompt, context)
        response = await self._llm.ainvoke(messages)
        return response.content or ""

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """스트리밍 텍스트 생성.

        LangChain Runnable의 astream()을 사용하여
        LangGraph stream_mode="messages"가 토큰을 캡처할 수 있도록 함.

        핵심: astream() 호출이 LangGraph의 이벤트 시스템에 의해 감지됨.

        Args:
            prompt: 사용자 프롬프트
            system_prompt: 시스템 프롬프트
            context: 추가 컨텍스트

        Yields:
            생성된 텍스트 청크
        """
        messages = self._build_messages(prompt, system_prompt, context)

        # astream() 호출 → LangGraph stream_mode="messages"가 캡처
        async for chunk in self._llm.astream(messages):
            content = chunk.content
            if content:
                yield content

    async def generate_structured(
        self,
        prompt: str,
        response_schema: type[T],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> T:
        """구조화된 응답 생성.

        LangChain의 with_structured_output() 사용.

        Args:
            prompt: 사용자 프롬프트
            response_schema: Pydantic BaseModel 서브클래스
            system_prompt: 시스템 프롬프트
            max_tokens: 최대 토큰 수 (무시됨)
            temperature: 생성 온도 (무시됨)

        Returns:
            response_schema 타입의 인스턴스
        """
        messages = self._build_messages(prompt, system_prompt)
        structured_llm = self._llm.with_structured_output(response_schema)

        try:
            result = await structured_llm.ainvoke(messages)
            logger.debug(
                "Structured output generated",
                extra={"schema": response_schema.__name__},
            )
            return result
        except Exception as e:
            logger.error(f"Structured output generation failed: {e}")
            raise


__all__ = ["LangChainLLMAdapter"]
