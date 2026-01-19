"""LangChain Runnable Wrapper - OpenAI SDK를 LangChain Runnable로 래핑.

기존 OpenAILLMClient를 유지하면서 LangGraph stream_mode="messages"와 통합.

아키텍처:
```
LangGraph astream(stream_mode="messages")
    │
    └── LangChainOpenAIRunnable (이 파일)
            │
            ├── _stream() → AIMessageChunk yield → stream_mode="messages" 캡처
            └── OpenAI SDK (기존 로직 재사용)
```

핵심:
- LangChain Runnable 인터페이스 구현 (astream, ainvoke)
- AIMessageChunk를 yield하여 LangGraph가 토큰 캡처 가능
- 기존 OpenAI SDK 호출 로직 유지

참고:
- https://docs.langchain.com/oss/python/langgraph/streaming#messages
- https://python.langchain.com/docs/how_to/custom_llm/
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from openai import AsyncOpenAI

from chat_worker.infrastructure.llm.config import (
    HTTP_LIMITS,
    HTTP_TIMEOUT,
    MAX_RETRIES,
)

logger = logging.getLogger(__name__)


class LangChainOpenAIRunnable(BaseChatModel):
    """OpenAI SDK를 LangChain Runnable로 래핑.

    LangGraph stream_mode="messages"가 토큰을 캡처할 수 있도록
    BaseChatModel을 구현하여 AIMessageChunk를 yield합니다.

    Usage:
        llm = LangChainOpenAIRunnable(model="gpt-4o")

        # LangGraph 노드에서 사용
        async for chunk in llm.astream(messages):
            # stream_mode="messages"에서 자동 캡처됨
            print(chunk.content)
    """

    model: str = "gpt-4o"
    """OpenAI 모델명."""

    temperature: float = 0.7
    """생성 온도."""

    max_tokens: int | None = None
    """최대 토큰 수."""

    api_key: str | None = None
    """OpenAI API 키 (None이면 환경변수 사용)."""

    _client: AsyncOpenAI | None = None
    """OpenAI 클라이언트 (내부용)."""

    class Config:
        """Pydantic 설정."""

        arbitrary_types_allowed = True

    def __init__(self, **kwargs: Any) -> None:
        """초기화."""
        super().__init__(**kwargs)
        http_client = httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            limits=HTTP_LIMITS,
        )
        self._client = AsyncOpenAI(
            api_key=self.api_key,
            http_client=http_client,
            max_retries=MAX_RETRIES,
        )
        logger.info(
            "LangChainOpenAIRunnable initialized",
            extra={"model": self.model},
        )

    @property
    def _llm_type(self) -> str:
        """LLM 타입 식별자."""
        return "langchain-openai-runnable"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        """모델 식별 파라미터."""
        return {
            "model": self.model,
            "temperature": self.temperature,
        }

    def _convert_messages(self, messages: list[BaseMessage]) -> list[dict[str, str]]:
        """LangChain 메시지를 OpenAI 포맷으로 변환."""
        result = []
        for msg in messages:
            role = "user"
            if msg.type == "system":
                role = "system"
            elif msg.type == "ai" or msg.type == "assistant":
                role = "assistant"
            elif msg.type == "human" or msg.type == "user":
                role = "user"

            content = msg.content
            if isinstance(content, list):
                # 멀티모달 메시지 처리
                content = json.dumps(content)

            result.append({"role": role, "content": str(content)})
        return result

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """동기 생성 (비권장 - async 사용 권장)."""
        raise NotImplementedError("Use async methods (ainvoke, astream)")

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """비동기 생성 (전체 응답).

        LangGraph ainvoke에서 호출됨.
        """
        openai_messages = self._convert_messages(messages)

        # max_tokens가 None이면 파라미터 제외 (OpenAI API 오류 방지)
        create_params: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": self.temperature,
            "stop": stop,
            "stream": False,
        }
        if self.max_tokens is not None:
            create_params["max_tokens"] = self.max_tokens

        response = await self._client.chat.completions.create(**create_params)

        content = response.choices[0].message.content or ""
        message = AIMessage(content=content)

        return ChatResult(
            generations=[ChatGeneration(message=message)],
        )

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """비동기 스트리밍 생성.

        LangGraph stream_mode="messages"에서 이 메서드의 출력을 캡처.
        AIMessageChunk를 yield하면 LangGraph가 토큰 이벤트로 전달.

        Args:
            messages: 입력 메시지 리스트
            stop: 중단 시퀀스
            run_manager: 콜백 매니저

        Yields:
            ChatGenerationChunk (AIMessageChunk 포함)
        """
        openai_messages = self._convert_messages(messages)

        # max_tokens가 None이면 파라미터 제외 (OpenAI API 오류 방지)
        create_params: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": self.temperature,
            "stop": stop,
            "stream": True,
        }
        if self.max_tokens is not None:
            create_params["max_tokens"] = self.max_tokens

        stream = await self._client.chat.completions.create(**create_params)

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content

                # AIMessageChunk yield → LangGraph stream_mode="messages" 캡처
                message_chunk = AIMessageChunk(content=content)
                generation_chunk = ChatGenerationChunk(message=message_chunk)

                # 콜백 호출 (LangGraph 이벤트 시스템 통합)
                if run_manager:
                    await run_manager.on_llm_new_token(content)

                yield generation_chunk

        logger.debug("LangChainOpenAIRunnable stream completed")


__all__ = ["LangChainOpenAIRunnable"]
