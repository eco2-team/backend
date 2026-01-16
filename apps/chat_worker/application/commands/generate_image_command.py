"""Generate Image Command.

이미지 생성 UseCase (Responses API).

Clean Architecture:
- Command(UseCase): 이 파일 - Port 호출, 오케스트레이션
- Port: ImageGeneratorPort - 이미지 생성 API 호출
- Node(Adapter): image_generation_node.py - LangGraph glue

아키텍처 의사결정:
- Chat Completions API: 기존 파이프라인 유지 (multi-intent 라우팅)
- Responses API: 이미지 생성 서브에이전트에서만 사용
- 같은 OpenAI API 키로 두 API 혼용 가능
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chat_worker.application.ports.image_generator import ImageGeneratorPort

logger = logging.getLogger(__name__)


# 프롬프트 길이 제한 (OpenAI gpt-image-1.5 기준)
MAX_PROMPT_LENGTH = 32000


@dataclass(frozen=True)
class GenerateImageInput:
    """Command 입력 DTO."""

    job_id: str
    prompt: str
    size: str = "1024x1024"
    quality: str = "medium"


@dataclass
class GenerateImageOutput:
    """Command 출력 DTO."""

    success: bool
    image_url: str | None = None
    description: str | None = None
    revised_prompt: str | None = None
    error_message: str | None = None
    events: list[str] = field(default_factory=list)


class GenerateImageCommand:
    """이미지 생성 Command (UseCase).

    Responses API의 네이티브 image_generation tool을 사용하여
    이미지를 생성합니다.

    플로우:
    1. 프롬프트 검증
    2. ImageGeneratorPort 호출 (Responses API)
    3. 결과 반환 (이미지 URL + 설명)

    Port 주입:
    - image_generator: ImageGeneratorPort 구현체
    """

    def __init__(
        self,
        image_generator: "ImageGeneratorPort",
    ) -> None:
        """Command 초기화.

        Args:
            image_generator: 이미지 생성 클라이언트
        """
        self._image_generator = image_generator

    async def execute(self, input_dto: GenerateImageInput) -> GenerateImageOutput:
        """Command 실행.

        Args:
            input_dto: 입력 DTO

        Returns:
            출력 DTO
        """
        events: list[str] = []

        # 1. 프롬프트 검증
        if not input_dto.prompt or not input_dto.prompt.strip():
            events.append("empty_prompt")
            logger.warning(
                "Empty prompt provided",
                extra={"job_id": input_dto.job_id},
            )
            return GenerateImageOutput(
                success=False,
                error_message="이미지 생성을 위한 설명이 필요해요.",
                events=events,
            )

        # 프롬프트 길이 검증
        if len(input_dto.prompt) > MAX_PROMPT_LENGTH:
            events.append("prompt_too_long")
            logger.warning(
                "Prompt too long",
                extra={
                    "job_id": input_dto.job_id,
                    "length": len(input_dto.prompt),
                    "max_length": MAX_PROMPT_LENGTH,
                },
            )
            return GenerateImageOutput(
                success=False,
                error_message="이미지 설명이 너무 길어요. 조금 더 간단하게 설명해 주세요.",
                events=events,
            )

        events.append("prompt_validated")

        # 2. 이미지 생성 API 호출
        try:
            logger.info(
                "Generating image",
                extra={
                    "job_id": input_dto.job_id,
                    "prompt_length": len(input_dto.prompt),
                    "size": input_dto.size,
                    "quality": input_dto.quality,
                },
            )

            result = await self._image_generator.generate(
                prompt=input_dto.prompt,
                size=input_dto.size,
                quality=input_dto.quality,
            )
            events.append("image_generated")

            logger.info(
                "Image generation completed",
                extra={
                    "job_id": input_dto.job_id,
                    "has_description": result.description is not None,
                },
            )

            return GenerateImageOutput(
                success=True,
                image_url=result.image_url,
                description=result.description,
                revised_prompt=result.revised_prompt,
                events=events,
            )

        except Exception as e:
            logger.error(
                "Image generation failed",
                extra={"job_id": input_dto.job_id, "error": str(e)},
            )
            events.append("image_generation_error")

            return GenerateImageOutput(
                success=False,
                error_message="이미지 생성 중 문제가 발생했어요. 다시 시도해 주세요.",
                events=events,
            )
