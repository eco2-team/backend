"""OpenAI Client Function Calling 단위 테스트.

Function Calling API 호출 및 결과 파싱 테스트.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_worker.infrastructure.llm.clients.openai_client import OpenAILLMClient


class TestOpenAIClientFunctionCalling:
    """OpenAI Client Function Calling 테스트."""

    @pytest.fixture
    def mock_openai_response(self):
        """Mock OpenAI 응답 팩토리."""

        def _create_response(func_name: str | None, func_args: str | None):
            mock_response = MagicMock()
            mock_message = MagicMock()

            if func_name and func_args:
                mock_function_call = MagicMock()
                mock_function_call.name = func_name
                mock_function_call.arguments = func_args
                mock_message.function_call = mock_function_call
            else:
                mock_message.function_call = None

            mock_response.choices = [MagicMock(message=mock_message)]
            return mock_response

        return _create_response

    @pytest.mark.asyncio
    async def test_function_call_success(self, mock_openai_response):
        """Function call 성공 시나리오."""
        mock_response = mock_openai_response("search_place", '{"query": "카페", "radius": 5000}')

        with patch(
            "chat_worker.infrastructure.llm.clients.openai_client.AsyncOpenAI"
        ) as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_openai.return_value = mock_client

            llm_client = OpenAILLMClient(model="gpt-5.2")

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

            func_name, func_args = await llm_client.generate_function_call(
                prompt="주변 카페 찾아줘",
                functions=functions,
                system_prompt="장소 검색 파라미터를 추출하세요",
            )

            assert func_name == "search_place"
            assert func_args == {"query": "카페", "radius": 5000}

            mock_client.chat.completions.create.assert_called_once()
            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert call_kwargs["model"] == "gpt-5.2"
            assert call_kwargs["functions"] == functions
            assert call_kwargs["function_call"] == "auto"

    @pytest.mark.asyncio
    async def test_function_call_forced(self, mock_openai_response):
        """Function call 강제 호출."""
        mock_response = mock_openai_response("get_weather", '{"needs_weather": true}')

        with patch(
            "chat_worker.infrastructure.llm.clients.openai_client.AsyncOpenAI"
        ) as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_openai.return_value = mock_client

            llm_client = OpenAILLMClient(model="gpt-5.2")

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
                function_call={"name": "get_weather"},
            )

            assert func_name == "get_weather"
            assert func_args == {"needs_weather": True}

            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert call_kwargs["function_call"] == {"name": "get_weather"}

    @pytest.mark.asyncio
    async def test_no_function_call(self, mock_openai_response):
        """Function call이 없는 경우."""
        mock_response = mock_openai_response(None, None)

        with patch(
            "chat_worker.infrastructure.llm.clients.openai_client.AsyncOpenAI"
        ) as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_openai.return_value = mock_client

            llm_client = OpenAILLMClient(model="gpt-5.2")

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
    async def test_invalid_json_arguments(self, mock_openai_response):
        """잘못된 JSON arguments."""
        mock_response = mock_openai_response("search_place", "{invalid json}")

        with patch(
            "chat_worker.infrastructure.llm.clients.openai_client.AsyncOpenAI"
        ) as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_openai.return_value = mock_client

            llm_client = OpenAILLMClient(model="gpt-5.2")

            functions = [{"name": "search_place", "parameters": {"type": "object"}}]

            with pytest.raises(ValueError, match="Invalid function arguments JSON"):
                await llm_client.generate_function_call(
                    prompt="테스트",
                    functions=functions,
                )

    @pytest.mark.asyncio
    async def test_system_prompt_included(self, mock_openai_response):
        """System prompt 포함 확인."""
        mock_response = mock_openai_response("test_func", "{}")

        with patch(
            "chat_worker.infrastructure.llm.clients.openai_client.AsyncOpenAI"
        ) as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_openai.return_value = mock_client

            llm_client = OpenAILLMClient(model="gpt-5.2")

            functions = [{"name": "test_func", "parameters": {"type": "object"}}]

            await llm_client.generate_function_call(
                prompt="테스트",
                functions=functions,
                system_prompt="시스템 프롬프트",
            )

            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            messages = call_kwargs["messages"]
            assert len(messages) == 2
            assert messages[0]["role"] == "system"
            assert messages[0]["content"] == "시스템 프롬프트"
            assert messages[1]["role"] == "user"
            assert messages[1]["content"] == "테스트"
