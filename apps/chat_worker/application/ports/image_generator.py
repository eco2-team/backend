"""Image Generator Port - 이미지 생성 추상 인터페이스.

Clean Architecture:
- Application Layer에서 정의하는 추상 Port
- Infrastructure Layer에서 Provider별 구현체 제공

지원 Provider:
- OpenAI: Responses API의 네이티브 image_generation tool (gpt-image-1.5)
- Gemini: Native Image Generation (gemini-3-pro-image-preview)

기능:
- 기본 이미지 생성: 프롬프트 기반
- 참조 이미지 생성: 캐릭터 스타일 일관성 (Gemini only)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ReferenceImage:
    """참조 이미지 DTO.

    Gemini 이미지 생성 시 스타일/캐릭터 참조용.
    URL 또는 bytes 중 하나만 제공하면 됩니다.
    URL만 제공 시 Gemini 호출 시점에 lazy fetch합니다.

    Attributes:
        image_url: CDN 이미지 URL (권장 - state가 가벼움)
        image_bytes: 이미지 바이트 데이터 (선택)
        mime_type: MIME 타입 (기본 image/png)
        description: 참조 이미지 설명 (선택)
    """

    image_url: str | None = None
    image_bytes: bytes | None = None
    mime_type: str = "image/png"
    description: str | None = None

    def __post_init__(self) -> None:
        """URL 또는 bytes 중 하나는 필수."""
        if not self.image_url and not self.image_bytes:
            raise ValueError("Either image_url or image_bytes must be provided")


@dataclass(frozen=True)
class ImageGenerationResult:
    """이미지 생성 결과 DTO.

    Attributes:
        image_url: 생성된 이미지 URL
        image_bytes: 이미지 바이트 (Provider에 따라 선택적)
        description: 모델이 생성한 이미지 설명
        revised_prompt: 모델이 수정한 프롬프트 (디버깅용)
        provider: 사용된 Provider (openai, gemini)
        model: 사용된 모델명
        width: 이미지 너비 (픽셀)
        height: 이미지 높이 (픽셀)
        has_synthid: SynthID 워터마크 포함 여부 (Gemini)
    """

    image_url: str
    image_bytes: bytes | None = None
    description: str | None = None
    revised_prompt: str | None = None
    provider: str | None = None
    model: str | None = None
    width: int | None = None
    height: int | None = None
    has_synthid: bool = False


class ImageGeneratorPort(ABC):
    """이미지 생성 Port.

    사용자 프롬프트를 기반으로 이미지를 생성합니다.

    구현체:
    - OpenAIResponsesImageGenerator: Responses API (gpt-image-1.5)
    - GeminiNativeImageGenerator: Gemini Native (gemini-3-pro-image-preview)

    사용 예시:
    ```python
    # 기본 생성
    result = await generator.generate(
        prompt="페트병 분리배출 방법 인포그래픽",
        size="1024x1024",
        quality="medium",
    )

    # 캐릭터 참조 생성 (Gemini)
    result = await generator.generate_with_reference(
        prompt="이 캐릭터가 분리배출하는 모습",
        reference_images=[ReferenceImage(image_bytes=char_bytes)],
    )
    ```
    """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "medium",
    ) -> ImageGenerationResult:
        """이미지 생성.

        Args:
            prompt: 생성할 이미지 설명
            size: 이미지 크기 (1024x1024, 1024x1792, 1792x1024)
            quality: 품질 (low, medium, high)

        Returns:
            ImageGenerationResult: 생성 결과

        Raises:
            ImageGenerationError: 생성 실패 시
        """
        pass

    async def generate_with_reference(
        self,
        prompt: str,
        reference_images: list[ReferenceImage],
        size: str = "1024x1024",
        quality: str = "medium",
    ) -> ImageGenerationResult:
        """참조 이미지를 기반으로 이미지 생성.

        캐릭터 스타일 일관성 유지를 위해 참조 이미지를 사용합니다.
        Gemini만 지원하며, OpenAI는 기본 generate()로 폴백합니다.

        Args:
            prompt: 생성할 이미지 설명
            reference_images: 참조 이미지 목록 (최대 5개 권장)
            size: 이미지 크기
            quality: 품질

        Returns:
            ImageGenerationResult: 생성 결과

        Raises:
            ImageGenerationError: 생성 실패 시
        """
        # 기본 구현: 참조 이미지 무시하고 기본 생성
        # Gemini 구현체에서 오버라이드
        return await self.generate(prompt, size, quality)

    @property
    def supports_reference_images(self) -> bool:
        """참조 이미지 지원 여부.

        Returns:
            True if 참조 이미지 지원 (Gemini)
        """
        return False

    @property
    def max_reference_images(self) -> int:
        """지원되는 최대 참조 이미지 개수.

        Returns:
            최대 개수 (0이면 미지원)
        """
        return 0


class ImageGenerationError(Exception):
    """이미지 생성 실패 예외."""

    def __init__(self, message: str, cause: Exception | None = None):
        super().__init__(message)
        self.cause = cause


class ReferenceImageNotSupportedError(ImageGenerationError):
    """참조 이미지 미지원 예외."""

    def __init__(self, provider: str):
        super().__init__(f"Reference images not supported by {provider}")
        self.provider = provider
