"""OpenAI Client Function Calling 단위 테스트.

Function Calling API 호출 및 결과 파싱 테스트.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from chat_worker.infrastructure.llm.clients.openai_client import OpenAILLMClient


class TestOpenAIClientFunctionCalling:
    """OpenAI Client Function Calling 테스트."""

    @pytest.fixture
    def mock_openai_client(self):
        """Mock OpenAI 클라이언트."""
        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        return mock_client

    @pytest.fixture
    def llm_client(self, mock_openai_client):
        """LLM 클라이언트 인스턴스."""
        client = OpenAILLMClient(model="gpt-5.2")
        client._client = mock_openai_client
        return client

    @pytest.mark.asyncio
    async def test_function_call_success(self, llm_client, mock_openai_client):
        """Function call 성공 시나리오."""
        # Mock 응답 설정
        mock_response = MagicMock()
        mock_message = MagicMock()
        mock_function_call = MagicMock()
        mock_function_call.name = "search_place"
        mock_function_call.arguments = '{"query": "카페", "radius": 5000}'
        mock_message.function_call = mock_function_call
        mock_response.choices = [MagicMock(message=mock_message)]

        mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

        # Function definition
        functions = [
            {
                "name": "search_place",
                "description": "장소 검색",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "radius": {"type": "integer"},
                    },
                    "required": ["query"],
                },
            }
        ]

        # 실행
        func_name, func_args = await llm_client.generate_function_call(
            prompt="주변 카페 찾아줘",
            functions=functions,
            system_prompt="장소 검색 파라미터를 추출하세요",
        )

        # 검증
        assert func_name == "search_place"
        assert func_args == {"query": "카페", "radius": 5000}

        # API 호출 확인
        mock_openai_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_openai_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-5.2"
        assert call_kwargs["functions"] == functions
        assert call_kwargs["function_call"] == "auto"

    @pytest.mark.asyncio
    async def test_function_call_forced(self, llm_client, mock_openai_client):
        """Function call 강제 호출."""
        mock_response = MagicMock()
        mock_message = MagicMock()
        mock_function_call = MagicMock()
        mock_function_call.name = "get_weather"
        mock_function_call.arguments = '{"needs_weather": true}'
        mock_message.function_call = mock_function_call
        mock_response.choices = [MagicMock(message=mock_message)]

        mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

        functions = [
            {
                "name": "get_weather",
                "description": "날씨 조회",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "needs_weather": {"type": "boolean"},
                    },
                    "required": ["needs_weather"],
                },
            }
        ]

        func_name, func_args = await llm_client.generate_function_call(
            prompt="종이 언제 버려?",
            functions=functions,
            function_call={"name": "get_weather"},  # 강제 호출
        )

        assert func_name == "get_weather"
        assert func_args == {"needs_weather": True}

        call_kwargs = mock_openai_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["function_call"] == {"name": "get_weather"}

    @pytest.mark.asyncio
    async def test_no_function_call(self, llm_client, mock_openai_client):
        """Function call이 없는 경우."""
        mock_response = MagicMock()
        mock_message = MagicMock()
        mock_message.function_call = None  # Function call 없음
        mock_response.choices = [MagicMock(message=mock_message)]

        mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

        functions = [
            {
                "name": "search_place",
                "description": "장소 검색",
                "parameters": {"type": "object", "properties": {}},
            }
        ]

        func_name, func_args = await llm_client.generate_function_call(
            prompt="안녕하세요",
            functions=functions,
        )

        assert func_name is None
        assert func_args is None

    @pytest.mark.asyncio
    async def test_invalid_json_arguments(self, llm_client, mock_openai_client):
        """잘못된 JSON arguments."""
        mock_response = MagicMock()
        mock_message = MagicMock()
        mock_function_call = MagicMock()
        mock_function_call.name = "search_place"
        mock_function_call.arguments = '{invalid json}'  # 잘못된 JSON
        mock_message.function_call = mock_function_call
        mock_response.choices = [MagicMock(message=mock_message)]

        mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

        functions = [{"name": "search_place", "parameters": {"type": "object"}}]

        with pytest.raises(ValueError, match="Invalid function arguments JSON"):
            await llm_client.generate_function_call(
                prompt="테스트",
                functions=functions,
            )

    @pytest.mark.asyncio
    async def test_system_prompt_included(self, llm_client, mock_openai_client):
        """System prompt 포함 확인."""
        mock_response = MagicMock()
        mock_message = MagicMock()
        mock_function_call = MagicMock()
        mock_function_call.name = "test_func"
        mock_function_call.arguments = '{}'
        mock_message.function_call = mock_function_call
        mock_response.choices = [MagicMock(message=mock_message)]

        mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

        functions = [{"name": "test_func", "parameters": {"type": "object"}}]

        await llm_client.generate_function_call(
            prompt="테스트",
            functions=functions,
            system_prompt="시스템 프롬프트",
        )

        call_kwargs = mock_openai_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "시스템 프롬프트"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "테스트"
