"""Google Gemini LLM Provider 구현."""

from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

from pydantic import BaseModel

from .base import ChatRequest, LLMProvider, VisionRequest
from .config import LLMConfig

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class GeminiProvider(LLMProvider):
    """Google Gemini API Provider.

    Gemini 2.0 Flash, Gemini 3.0 Flash 등 지원.
    Vision 및 Chat Completion 통합 API 사용.

    Note:
        google-generativeai 패키지 필요:
        pip install google-generativeai
    """

    def __init__(self, config: LLMConfig):
        self._config = config
        self._client = None

    @property
    def name(self) -> str:
        return "gemini"

    def _get_client(self):
        """Lazy import 및 클라이언트 초기화."""
        if self._client is None:
            try:
                import google.generativeai as genai

                genai.configure(api_key=self._config.api_key)
                self._client = genai
            except ImportError as e:
                raise ImportError(
                    "google-generativeai 패키지가 필요합니다. " "pip install google-generativeai"
                ) from e
        return self._client

    def _get_model(self, model_name: str):
        """Gemini 모델 인스턴스 반환."""
        genai = self._get_client()
        return genai.GenerativeModel(model_name)

    def _parse_response(
        self,
        response_text: str,
        response_model: type[T],
    ) -> dict[str, Any]:
        """Gemini 응답을 Pydantic 모델로 파싱."""
        # JSON 블록 추출 (```json ... ``` 형식 처리)
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            data = json.loads(text)
            parsed = response_model.model_validate(data)
            return parsed.model_dump()
        except (json.JSONDecodeError, Exception) as e:
            logger.error(
                "Gemini response parsing failed",
                extra={"error": str(e), "response": text[:500]},
            )
            raise ValueError(f"Failed to parse Gemini response: {e}") from e

    def _build_schema_prompt(self, response_model: type[T]) -> str:
        """Pydantic 모델에서 JSON 스키마 프롬프트 생성."""
        schema = response_model.model_json_schema()
        return f"""
응답은 반드시 다음 JSON 스키마를 따르는 유효한 JSON 형식이어야 합니다:

```json
{json.dumps(schema, ensure_ascii=False, indent=2)}
```

JSON만 출력하세요. 다른 텍스트는 포함하지 마세요.
"""

    def vision_analyze_sync(
        self,
        request: VisionRequest,
        response_model: type[T],
    ) -> dict[str, Any]:
        """Gemini Vision API 동기 호출."""
        import httpx

        model = self._get_model(self._config.vision_model)

        # 이미지 다운로드
        image_data = httpx.get(request.image_url).content

        # 프롬프트 구성
        prompt_parts = []
        if request.system_prompt:
            prompt_parts.append(request.system_prompt)
        prompt_parts.append(request.prompt)
        prompt_parts.append(self._build_schema_prompt(response_model))

        full_prompt = "\n\n".join(prompt_parts)

        logger.info(
            "Gemini Vision sync call",
            extra={"model": self._config.vision_model},
        )

        response = model.generate_content(
            [
                {"mime_type": "image/jpeg", "data": image_data},
                full_prompt,
            ],
            generation_config={"response_mime_type": "application/json"},
        )

        return self._parse_response(response.text, response_model)

    async def vision_analyze(
        self,
        request: VisionRequest,
        response_model: type[T],
    ) -> dict[str, Any]:
        """Gemini Vision API 비동기 호출."""
        import httpx

        model = self._get_model(self._config.vision_model)

        # 이미지 비동기 다운로드
        async with httpx.AsyncClient() as client:
            resp = await client.get(request.image_url)
            image_data = resp.content

        # 프롬프트 구성
        prompt_parts = []
        if request.system_prompt:
            prompt_parts.append(request.system_prompt)
        prompt_parts.append(request.prompt)
        prompt_parts.append(self._build_schema_prompt(response_model))

        full_prompt = "\n\n".join(prompt_parts)

        logger.info(
            "Gemini Vision async call",
            extra={"model": self._config.vision_model},
        )

        # Gemini는 동기 API만 제공, 비동기 래핑 필요
        response = await model.generate_content_async(
            [
                {"mime_type": "image/jpeg", "data": image_data},
                full_prompt,
            ],
            generation_config={"response_mime_type": "application/json"},
        )

        return self._parse_response(response.text, response_model)

    def chat_completion_sync(
        self,
        request: ChatRequest,
        response_model: type[T],
    ) -> dict[str, Any]:
        """Gemini Chat Completion 동기 호출."""
        model = self._get_model(self._config.chat_model)

        # 메시지 변환 (OpenAI 형식 → Gemini 형식)
        prompt_parts = []
        if request.system_prompt:
            prompt_parts.append(request.system_prompt)

        for msg in request.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt_parts.insert(0, content)
            else:
                prompt_parts.append(content)

        prompt_parts.append(self._build_schema_prompt(response_model))
        full_prompt = "\n\n".join(prompt_parts)

        logger.info(
            "Gemini Chat sync call",
            extra={"model": self._config.chat_model},
        )

        response = model.generate_content(
            full_prompt,
            generation_config={"response_mime_type": "application/json"},
        )

        return self._parse_response(response.text, response_model)

    async def chat_completion(
        self,
        request: ChatRequest,
        response_model: type[T],
    ) -> dict[str, Any]:
        """Gemini Chat Completion 비동기 호출."""
        model = self._get_model(self._config.chat_model)

        # 메시지 변환
        prompt_parts = []
        if request.system_prompt:
            prompt_parts.append(request.system_prompt)

        for msg in request.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt_parts.insert(0, content)
            else:
                prompt_parts.append(content)

        prompt_parts.append(self._build_schema_prompt(response_model))
        full_prompt = "\n\n".join(prompt_parts)

        logger.info(
            "Gemini Chat async call",
            extra={"model": self._config.chat_model},
        )

        response = await model.generate_content_async(
            full_prompt,
            generation_config={"response_mime_type": "application/json"},
        )

        return self._parse_response(response.text, response_model)
