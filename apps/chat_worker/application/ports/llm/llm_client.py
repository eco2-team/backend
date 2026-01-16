"""LLM Client Port - 순수 LLM API 호출.

책임:
- 텍스트 생성 (generate)
- 스트리밍 생성 (generate_stream)
- 구조화된 응답 생성 (generate_structured)

포함하지 않는 것 (LLMPolicy로 분리):
- 프롬프트 템플릿
- 모델 선택/라우팅
- 리트라이 정책
- 레이트리밋

참고:
- OpenAI Structured Outputs: https://platform.openai.com/docs/guides/structured-outputs
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
