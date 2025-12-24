"""Google Gemini LLM Provider 구현.

Gemini 3 Flash, Gemini 2.5 Flash 등 최신 모델 지원.
새로운 Gen AI SDK (google-genai) 사용.

Ref: https://ai.google.dev/gemini-api/docs?hl=ko
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, TypeVar

from pydantic import BaseModel

from .base import ChatRequest, LLMProvider, VisionRequest
from .config import LLMConfig

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class GeminiProvider(LLMProvider):
    """Google Gemini API Provider.

    Gemini 3 Flash, Gemini 2.5 Flash/Pro 등 지원.
    Gen AI SDK (google-genai) 사용.

    Note:
        google-genai 패키지 필요:
        pip install google-genai

    Models:
        - gemini-3-flash-preview: 프론티어급 성능, 합리적인 비용
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
                from google import genai

                os.environ.setdefault("GOOGLE_API_KEY", self._config.api_key)
                self._client = genai.Client(api_key=self._config.api_key)
            except ImportError as e:
                raise ImportError(
                    "google-genai 패키지가 필요합니다. pip install google-genai"
                ) from e
        return self._client

    def _parse_response(
        self,
        response_text: str,
        response_model: type[T],
    ) -> dict[str, Any]:
        """Gemini 응답을 Pydantic 모델로 파싱."""
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

        client = self._get_client()

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

        # Gen AI SDK 사용 (JSON 모드 강제)
        response = client.models.generate_content(
            model=self._config.vision_model,
            contents=[
                {"inline_data": {"mime_type": "image/jpeg", "data": image_data}},
                full_prompt,
            ],
            config={"response_mime_type": "application/json"},
        )

        return self._parse_response(response.text, response_model)

    async def vision_analyze(
        self,
        request: VisionRequest,
        response_model: type[T],
    ) -> dict[str, Any]:
        """Gemini Vision API 비동기 호출."""
        import asyncio

        import httpx

        client = self._get_client()

        # 이미지 비동기 다운로드
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.get(request.image_url)
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

        # Gen AI SDK는 동기만 지원, 스레드풀로 비동기 래핑 (JSON 모드 강제)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=self._config.vision_model,
                contents=[
                    {"inline_data": {"mime_type": "image/jpeg", "data": image_data}},
                    full_prompt,
                ],
                config={"response_mime_type": "application/json"},
            ),
        )

        return self._parse_response(response.text, response_model)

    def chat_completion_sync(
        self,
        request: ChatRequest,
        response_model: type[T],
    ) -> dict[str, Any]:
        """Gemini Chat Completion 동기 호출."""
        client = self._get_client()

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

        response = client.models.generate_content(
            model=self._config.chat_model,
            contents=full_prompt,
            config={"response_mime_type": "application/json"},
        )

        return self._parse_response(response.text, response_model)

    async def chat_completion(
        self,
        request: ChatRequest,
        response_model: type[T],
    ) -> dict[str, Any]:
        """Gemini Chat Completion 비동기 호출."""
        import asyncio

        client = self._get_client()

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

        # Gen AI SDK는 동기만 지원, 스레드풀로 비동기 래핑 (JSON 모드 강제)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=self._config.chat_model,
                contents=full_prompt,
                config={"response_mime_type": "application/json"},
            ),
        )

        return self._parse_response(response.text, response_model)
