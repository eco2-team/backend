"""Gemini Native Image Generator (Nano Banana).

Gemini의 네이티브 이미지 생성 기능을 사용한 이미지 생성.

지원 모델 (Nano Banana):
- gemini-3-pro-image-preview: 전문가급 품질, 참조 이미지 최대 14개, image_size 지원
- gemini-2.5-flash-image: 빠른 생성, 참조 이미지 최대 3개

특징:
- 참조 이미지 기반 스타일 일관성 (캐릭터 참조)
- 멀티턴 대화 지원 (이전 생성 결과 참조 가능)
- TEXT + IMAGE 혼합 응답
- SynthID 워터마크 자동 포함

API 문서: https://ai.google.dev/gemini-api/docs/image-generation
"""

from __future__ import annotations

import base64
import logging
import os

from google import genai
from google.genai import types

from chat_worker.application.ports.image_generator import (
    ImageGenerationError,
    ImageGenerationResult,
    ImageGeneratorPort,
    ReferenceImage,
)

logger = logging.getLogger(__name__)

# Gemini 모델별 참조 이미지 제한
MODEL_REFERENCE_LIMITS = {
    "gemini-3-pro-image-preview": 14,  # 캐릭터 5개 포함
    "gemini-2.5-flash-image": 3,
}

# Aspect Ratio 매핑 (size → aspect_ratio)
SIZE_TO_ASPECT_RATIO = {
    "1024x1024": "1:1",
    "1024x1792": "9:16",
    "1792x1024": "16:9",
    "512x512": "1:1",
}

# Quality → Image Size 매핑 (Pro 모델만 지원)
QUALITY_TO_IMAGE_SIZE = {
    "low": None,  # 기본값 사용
    "medium": "1K",
    "high": "2K",
}


class GeminiNativeImageGenerator(ImageGeneratorPort):
    """Gemini Native Image Generator.

    Gemini의 네이티브 이미지 생성 기능을 사용합니다.

    특징:
    - 참조 이미지 기반 스타일 일관성 (캐릭터 참조)
    - 멀티턴 대화 지원
    - TEXT + IMAGE 혼합 응답

    사용 예시:
    ```python
    generator = GeminiNativeImageGenerator()

    # 기본 생성
    result = await generator.generate("페트병 분리배출 인포그래픽")

    # 캐릭터 참조 생성
    result = await generator.generate_with_reference(
        prompt="이 캐릭터가 분리배출하는 모습",
        reference_images=[ReferenceImage(image_bytes=char_bytes)],
    )
    ```
    """

    def __init__(
        self,
        model: str = "gemini-3-pro-image-preview",
        api_key: str | None = None,
    ):
        """초기화.

        Args:
            model: Gemini 이미지 모델 (기본 gemini-3-pro-image-preview)
            api_key: API 키 (None이면 환경변수 GOOGLE_API_KEY)

        Raises:
            ValueError: API 키가 없는 경우
        """
        self._model = model
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        if not self._api_key:
            raise ValueError(
                "Google API key required. Set GOOGLE_API_KEY environment variable "
                "or pass api_key parameter."
            )
        self._client = genai.Client(api_key=self._api_key)
        self._max_reference = MODEL_REFERENCE_LIMITS.get(model, 3)

    @property
    def supports_reference_images(self) -> bool:
        """참조 이미지 지원 여부."""
        return True

    @property
    def max_reference_images(self) -> int:
        """지원되는 최대 참조 이미지 개수."""
        return self._max_reference

    async def generate(
        self,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "medium",
    ) -> ImageGenerationResult:
        """이미지 생성 (참조 없음).

        Args:
            prompt: 생성할 이미지 설명
            size: 이미지 크기 (aspect_ratio로 변환)
            quality: 품질 (Pro 모델: 1K/2K, Flash: 무시)

        Returns:
            ImageGenerationResult: 생성 결과
        """
        return await self._generate_internal(
            prompt=prompt,
            size=size,
            quality=quality,
            reference_images=None,
        )

    async def generate_with_reference(
        self,
        prompt: str,
        reference_images: list[ReferenceImage],
        size: str = "1024x1024",
        quality: str = "medium",
    ) -> ImageGenerationResult:
        """참조 이미지를 기반으로 이미지 생성.

        캐릭터 스타일 일관성을 위해 참조 이미지를 사용합니다.

        Args:
            prompt: 생성할 이미지 설명
            reference_images: 참조 이미지 목록
            size: 이미지 크기 (aspect_ratio로 변환)
            quality: 품질 (Pro 모델: 1K/2K, Flash: 무시)

        Returns:
            ImageGenerationResult: 생성 결과
        """
        # 참조 이미지 개수 제한
        if len(reference_images) > self._max_reference:
            logger.warning(
                "Too many reference images: %d > %d, truncating",
                len(reference_images),
                self._max_reference,
            )
            reference_images = reference_images[: self._max_reference]

        return await self._generate_internal(
            prompt=prompt,
            size=size,
            quality=quality,
            reference_images=reference_images,
        )

    async def _generate_internal(
        self,
        prompt: str,
        size: str,
        quality: str,
        reference_images: list[ReferenceImage] | None,
    ) -> ImageGenerationResult:
        """내부 이미지 생성 로직.

        Args:
            prompt: 생성 프롬프트
            size: 이미지 크기 (aspect_ratio로 변환)
            quality: 품질 (Pro 모델에서 image_size로 변환)
            reference_images: 참조 이미지 (선택)

        Returns:
            ImageGenerationResult
        """
        aspect_ratio = SIZE_TO_ASPECT_RATIO.get(size, "1:1")
        # Pro 모델만 image_size 지원
        image_size = QUALITY_TO_IMAGE_SIZE.get(quality) if "pro" in self._model.lower() else None

        logger.info(
            "Generating image (model=%s, aspect_ratio=%s, image_size=%s, references=%d)",
            self._model,
            aspect_ratio,
            image_size,
            len(reference_images) if reference_images else 0,
        )

        try:
            # 콘텐츠 구성
            parts: list[types.Part] = []

            # 참조 이미지 추가
            if reference_images:
                parts.append(
                    types.Part.from_text(
                        "다음 참조 이미지의 캐릭터 스타일을 유지하면서 이미지를 생성해주세요:"
                    )
                )
                for ref in reference_images:
                    parts.append(
                        types.Part.from_bytes(
                            data=ref.image_bytes,
                            mime_type=ref.mime_type,
                        )
                    )
                parts.append(types.Part.from_text(f"\n요청: {prompt}"))
            else:
                parts.append(types.Part.from_text(prompt))

            # ImageConfig 구성 (aspect_ratio + image_size)
            image_config = types.ImageConfig(aspect_ratio=aspect_ratio)
            if image_size:
                image_config = types.ImageConfig(
                    aspect_ratio=aspect_ratio,
                    image_size=image_size,
                )

            # Gemini API 호출 (Nano Banana)
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=types.Content(parts=parts),
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                    image_config=image_config,
                ),
            )

            # 응답 파싱
            image_bytes = None
            description = None

            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    # 이미지 데이터
                    image_bytes = part.inline_data.data
                elif part.text:
                    # 텍스트 설명
                    description = part.text

            if not image_bytes:
                raise ImageGenerationError("No image generated in response")

            # 이미지를 Base64 Data URL로 변환
            # Gemini는 URL 대신 바이트를 반환하므로 Data URL 생성
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            image_url = f"data:image/png;base64,{image_b64}"

            logger.info(
                "Image generated successfully (size=%d bytes)",
                len(image_bytes),
            )

            return ImageGenerationResult(
                image_url=image_url,
                image_bytes=image_bytes,
                description=description,
                provider="google",
                model=self._model,
            )

        except ImageGenerationError:
            raise
        except Exception as e:
            logger.error("Gemini image generation failed: %s", e)
            raise ImageGenerationError(
                f"Failed to generate image: {e}",
                cause=e,
            ) from e
