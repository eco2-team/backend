"""OpenAI Responses API Image Generator.

Responses API의 네이티브 image_generation tool을 사용한 이미지 생성.

아키텍처 의사결정:
- Chat Completions API (기존): 이미지 생성 미지원
- Images API (직접): 단순 이미지 생성만
- Responses API (선택): 모델이 프롬프트 최적화 + 이미지 생성 + 설명 텍스트

왜 Responses API?
1. 모델이 프롬프트를 최적화하여 더 나은 이미지 생성
2. 이미지와 함께 설명 텍스트 자동 생성
3. 같은 OpenAI API 키로 Chat Completions와 혼용 가능
4. 기존 LangGraph 파이프라인 구조 유지

캐릭터 참조:
- Responses API input에 이미지 URL 포함하여 스타일 참조 가능
- Gemini만큼 강력하지 않지만 기본적인 스타일 가이드 제공

비용 (gpt-image-1.5, 1024x1024 기준):
- low: ~$0.02
- medium: ~$0.07
- high: ~$0.19
+ Responses API 토큰 비용 추가
"""

from __future__ import annotations

import base64
import logging
import os

import httpx
from openai import AsyncOpenAI

from chat_worker.application.ports.image_generator import (
    ImageGenerationError,
    ImageGenerationResult,
    ImageGeneratorPort,
    ReferenceImage,
)

logger = logging.getLogger(__name__)

# 이미지 생성 타임아웃 (초) - DALL-E는 10-30초 소요
# connect: 연결 대기, read: 응답 대기, write: 요청 전송, pool: 커넥션 풀 대기
DEFAULT_IMAGE_TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=5.0, pool=5.0)


class OpenAIResponsesImageGenerator(ImageGeneratorPort):
    """OpenAI Responses API 이미지 생성기.

    네이티브 image_generation tool을 사용하여
    모델이 프롬프트를 최적화하고 이미지를 생성합니다.

    장점:
    - 모델이 프롬프트 최적화 (더 나은 결과)
    - 이미지 + 설명 텍스트 동시 생성
    - 대화 컨텍스트 활용 가능

    사용 예시:
    ```python
    generator = OpenAIResponsesImageGenerator()
    result = await generator.generate(
        prompt="페트병 분리배출 방법을 단계별로 보여주는 인포그래픽",
        quality="medium",
    )
    print(result.image_url)
    print(result.description)
    ```
    """

    def __init__(
        self,
        model: str = "gpt-5.2",
        api_key: str | None = None,
        default_size: str = "1024x1024",
        default_quality: str = "medium",
    ):
        """초기화.

        Args:
            model: Responses API 모델 (프롬프트 최적화용, 기본 LLM과 동일)
            api_key: API 키 (None이면 환경변수 OPENAI_API_KEY)
            default_size: 기본 이미지 크기
            default_quality: 기본 품질 (low, medium, high)
        """
        self._model = model
        self._client = AsyncOpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            timeout=DEFAULT_IMAGE_TIMEOUT,
        )
        self._default_size = default_size
        self._default_quality = default_quality

    async def generate(
        self,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "medium",
    ) -> ImageGenerationResult:
        """이미지 생성 (Responses API).

        Args:
            prompt: 생성할 이미지 설명
            size: 이미지 크기 (1024x1024, 1024x1792, 1792x1024)
            quality: 품질 (low, medium, high)

        Returns:
            ImageGenerationResult: 생성된 이미지 URL + 설명

        Raises:
            ImageGenerationError: 생성 실패 시
        """
        size = size or self._default_size
        quality = quality or self._default_quality

        logger.info(
            "Generating image (model=%s, size=%s, quality=%s)",
            self._model,
            size,
            quality,
        )

        try:
            # Responses API with native image_generation tool
            response = await self._client.responses.create(
                model=self._model,
                input=self._build_input_prompt(prompt),
                tools=[
                    {
                        "type": "image_generation",
                        "image_generation": {
                            "size": size,
                            "quality": quality,
                        },
                    }
                ],
            )

            # 응답에서 이미지 URL과 텍스트 추출
            image_url = None
            description = None
            revised_prompt = None

            for item in response.output:
                if item.type == "image_generation_call":
                    # 이미지 생성 결과
                    image_url = item.result
                    revised_prompt = getattr(item, "revised_prompt", None)
                elif item.type == "message":
                    # 텍스트 응답 (설명)
                    if item.content and len(item.content) > 0:
                        description = item.content[0].text

            if not image_url:
                raise ImageGenerationError(
                    "No image generated in response",
                )

            logger.info(
                "Image generated successfully (url=%s...)",
                image_url[:50] if image_url else "None",
            )

            return ImageGenerationResult(
                image_url=image_url,
                description=description,
                revised_prompt=revised_prompt,
                provider="openai",
                model=self._model,
            )

        except ImageGenerationError:
            raise
        except Exception as e:
            logger.error("Image generation failed: %s", e)
            raise ImageGenerationError(
                f"Failed to generate image: {e}",
                cause=e,
            ) from e

    @property
    def supports_reference_images(self) -> bool:
        """참조 이미지 지원 여부."""
        return True

    @property
    def max_reference_images(self) -> int:
        """지원되는 최대 참조 이미지 개수.

        OpenAI Responses API는 입력에 이미지를 포함할 수 있지만,
        Gemini처럼 네이티브 참조는 아님. 1개만 권장.
        """
        return 1

    async def generate_with_reference(
        self,
        prompt: str,
        reference_images: list[ReferenceImage],
        size: str = "1024x1024",
        quality: str = "medium",
    ) -> ImageGenerationResult:
        """참조 이미지를 기반으로 이미지 생성.

        OpenAI Responses API는 입력에 이미지를 포함하여
        모델이 스타일을 참고하도록 할 수 있습니다.

        Args:
            prompt: 생성할 이미지 설명
            reference_images: 참조 이미지 목록 (첫 번째만 사용)
            size: 이미지 크기
            quality: 품질

        Returns:
            ImageGenerationResult: 생성 결과
        """
        size = size or self._default_size
        quality = quality or self._default_quality

        # 첫 번째 참조 이미지만 사용
        reference = reference_images[0] if reference_images else None

        logger.info(
            "Generating image with reference (model=%s, size=%s, has_ref=%s)",
            self._model,
            size,
            reference is not None,
        )

        try:
            # 참조 이미지가 있으면 멀티모달 입력 구성
            if reference:
                input_content = self._build_multimodal_input(prompt, reference)
            else:
                input_content = self._build_input_prompt(prompt)

            response = await self._client.responses.create(
                model=self._model,
                input=input_content,
                tools=[
                    {
                        "type": "image_generation",
                        "image_generation": {
                            "size": size,
                            "quality": quality,
                        },
                    }
                ],
            )

            # 응답 파싱
            image_url = None
            description = None
            revised_prompt = None

            for item in response.output:
                if item.type == "image_generation_call":
                    image_url = item.result
                    revised_prompt = getattr(item, "revised_prompt", None)
                elif item.type == "message":
                    if item.content and len(item.content) > 0:
                        description = item.content[0].text

            if not image_url:
                raise ImageGenerationError("No image generated in response")

            logger.info(
                "Image generated with reference (url=%s...)",
                image_url[:50] if image_url else "None",
            )

            return ImageGenerationResult(
                image_url=image_url,
                description=description,
                revised_prompt=revised_prompt,
                provider="openai",
                model=self._model,
            )

        except ImageGenerationError:
            raise
        except Exception as e:
            logger.error("Image generation with reference failed: %s", e)
            raise ImageGenerationError(
                f"Failed to generate image: {e}",
                cause=e,
            ) from e

    def _build_input_prompt(self, user_prompt: str) -> str:
        """Responses API 입력 프롬프트 구성.

        Args:
            user_prompt: 사용자 프롬프트

        Returns:
            최적화된 입력 프롬프트
        """
        return f"""다음 요청에 맞는 이미지를 생성해주세요.

요청: {user_prompt}

이미지 생성 후, 생성된 이미지에 대한 간단한 설명도 함께 제공해주세요.
설명은 한국어로 작성해주세요."""

    def _build_multimodal_input(
        self,
        user_prompt: str,
        reference: ReferenceImage,
    ) -> list[dict]:
        """참조 이미지를 포함한 멀티모달 입력 구성.

        Args:
            user_prompt: 사용자 프롬프트
            reference: 참조 이미지

        Returns:
            멀티모달 입력 (텍스트 + 이미지)
        """
        # Base64 인코딩
        image_b64 = base64.b64encode(reference.image_bytes).decode("utf-8")
        data_url = f"data:{reference.mime_type};base64,{image_b64}"

        return [
            {
                "type": "input_text",
                "text": f"""다음 캐릭터 이미지의 스타일을 참고하여 새로운 이미지를 생성해주세요.

캐릭터 스타일:
- 이 캐릭터의 색상, 형태, 분위기를 유지해주세요
- 친근하고 귀여운 느낌을 살려주세요

요청: {user_prompt}

이미지 생성 후, 생성된 이미지에 대한 간단한 설명도 함께 제공해주세요.
설명은 한국어로 작성해주세요.""",
            },
            {
                "type": "input_image",
                "image_url": data_url,
            },
        ]
