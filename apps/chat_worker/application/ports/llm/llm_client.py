"""LLM Client Port - 순수 LLM API 호출.

책임:
- 텍스트 생성 (generate)
- 스트리밍 생성 (generate_stream)
- 구조화된 응답 생성 (generate_structured)
- 네이티브 도구 사용 생성 (generate_with_tools)
- 함수 호출 (generate_function_call)

포함하지 않는 것 (LLMPolicy로 분리):
- 프롬프트 템플릿
- 모델 선택/라우팅
- 리트라이 정책
- 레이트리밋

참고:
- OpenAI Structured Outputs: https://platform.openai.com/docs/guides/structured-outputs
- OpenAI Responses API: https://platform.openai.com/docs/api-reference/responses
- OpenAI Function Calling: https://platform.openai.com/docs/guides/function-calling
- Gemini Structured Output: https://ai.google.dev/gemini-api/docs/structured-output
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMClientPort(ABC):
    """LLM 클라이언트 포트.

    순수 API 호출만 담당.
    OpenAI, Gemini 등 구현체를 DI로 주입.
    """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """텍스트 생성.

        Args:
            prompt: 사용자 프롬프트
            system_prompt: 시스템 프롬프트
            context: 추가 컨텍스트 (JSON으로 변환)
            max_tokens: 최대 토큰 수
            temperature: 생성 온도

        Returns:
            생성된 텍스트
        """
        pass

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """스트리밍 텍스트 생성.

        Args:
            prompt: 사용자 프롬프트
            system_prompt: 시스템 프롬프트
            context: 추가 컨텍스트 (JSON으로 변환)

        Yields:
            생성된 텍스트 청크
        """
        pass

    async def generate_structured(
        self,
        prompt: str,
        response_schema: type[T],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> T:
        """구조화된 응답 생성 (Structured Output).

        JSON 스키마를 준수하는 응답을 생성합니다.
        파싱 실패 없이 타입 안전한 결과를 보장합니다.

        Args:
            prompt: 사용자 프롬프트
            response_schema: Pydantic BaseModel 서브클래스
            system_prompt: 시스템 프롬프트
            max_tokens: 최대 토큰 수
            temperature: 생성 온도

        Returns:
            response_schema 타입의 인스턴스

        Note:
            기본 구현은 generate()를 호출하고 JSON 파싱을 시도합니다.
            OpenAI/Gemini 구현체는 네이티브 Structured Output API를 사용합니다.
        """
        import json

        # 스키마 정보를 프롬프트에 추가
        schema_info = response_schema.model_json_schema()
        enhanced_prompt = (
            f"{prompt}\n\n"
            f"응답은 반드시 다음 JSON 스키마를 준수해야 합니다:\n"
            f"```json\n{json.dumps(schema_info, indent=2, ensure_ascii=False)}\n```"
        )

        response = await self.generate(
            prompt=enhanced_prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        # JSON 파싱 시도
        try:
            # ```json ... ``` 블록 추출
            import re

            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response.strip()

            data = json.loads(json_str)
            return response_schema.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(f"Failed to parse structured response: {e}") from e

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[str],
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """네이티브 도구를 사용한 스트리밍 생성.

        OpenAI Responses API 또는 Gemini Google Search를 통해
        네이티브 도구(web_search 등)를 사용하여 응답을 생성합니다.

        Args:
            prompt: 사용자 프롬프트
            tools: 사용할 도구 목록 (예: ["web_search"])
            system_prompt: 시스템 프롬프트
            context: 추가 컨텍스트 (JSON으로 변환)

        Yields:
            생성된 텍스트 청크

        Note:
            기본 구현은 도구 없이 일반 generate_stream을 호출합니다.
            OpenAI/Gemini 구현체는 네이티브 tool API를 사용합니다.
        """
        # 기본 구현: 도구 없이 일반 스트리밍
        async for chunk in self.generate_stream(
            prompt=prompt,
            system_prompt=system_prompt,
            context=context,
        ):
            yield chunk

    async def generate_function_call(
        self,
        prompt: str,
        functions: list[dict[str, Any]],
        system_prompt: str | None = None,
        function_call: str | dict[str, str] = "auto",
    ) -> tuple[str | None, dict[str, Any] | None]:
        """Function Calling API 호출.

        LLM에게 function definitions을 제공하고, LLM이 어떤 함수를
        어떤 인자로 호출해야 할지 결정하도록 합니다.

        Args:
            prompt: 사용자 메시지
            functions: OpenAI function definitions 리스트.
                각 function은 name, description, parameters를 포함.
                예: [{"name": "search", "description": "...", "parameters": {...}}]
            system_prompt: 시스템 프롬프트 (선택)
            function_call: 함수 호출 제어.
                - "auto": LLM이 자동 결정 (기본값)
                - "none": 함수 호출하지 않음
                - {"name": "function_name"}: 특정 함수 강제 호출

        Returns:
            (function_name, arguments) 튜플
            - function_name: 호출할 함수 이름 (None이면 함수 호출 안함)
            - arguments: 함수 인자 dict (JSON 파싱됨)

        Raises:
            ValueError: JSON 파싱 실패 시
            NotImplementedError: 구현체가 Function Calling을 지원하지 않을 때

        Note:
            기본 구현은 NotImplementedError를 발생시킵니다.
            OpenAI 구현체는 Chat Completions API의 functions 파라미터를 사용합니다.

        Example:
            >>> functions = [{
            ...     "name": "search_place",
            ...     "description": "장소 검색",
            ...     "parameters": {
            ...         "type": "object",
            ...         "properties": {
            ...             "query": {"type": "string", "description": "검색어"},
            ...             "radius": {"type": "integer", "description": "반경(m)"}
            ...         },
            ...         "required": ["query"]
            ...     }
            ... }]
            >>> name, args = await llm.generate_function_call(
            ...     prompt="주변 카페 찾아줘",
            ...     functions=functions
            ... )
            >>> # name == "search_place"
            >>> # args == {"query": "카페", "radius": 5000}
        """
        raise NotImplementedError(
            "generate_function_call() is not implemented. "
            "Override this method in the implementation class."
        )
