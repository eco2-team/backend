"""Generate Image Command.

이미지 생성 UseCase (Responses API).

Clean Architecture:
- Command(UseCase): 이 파일 - Port 호출, 오케스트레이션
- Port: ImageGeneratorPort - 이미지 생성 API 호출
- Port: PromptLoaderPort - 프롬프트 로딩
- Node(Adapter): image_generation_node.py - LangGraph glue

아키텍처 의사결정:
- Chat Completions API: 기존 파이프라인 유지 (multi-intent 라우팅)
- Responses API: 이미지 생성 서브에이전트에서만 사용
- 같은 OpenAI API 키로 두 API 혼용 가능

캐릭터 참조 이미지:
- character_context.asset에서 캐릭터 참조 이미지 가져옴
- generate_with_reference()로 캐릭터 스타일 반영

프롬프트 관리:
- assets/prompts/image_generation/ 에서 프롬프트 로드
- character_reference.txt: 캐릭터 참조 이미지 생성용
- reference_only.txt: 캐릭터 정보 없이 참조 이미지만 사용
- basic.txt: 기본 이미지 생성용
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chat_worker.application.ports.image_generator import (
        ImageGeneratorPort,
    )
    from chat_worker.application.ports.prompt_loader import PromptLoaderPort

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
    reference_image_url: str | None = None  # 캐릭터 참조 이미지 CDN URL (lazy fetch)
    reference_image_mime: str = "image/png"  # 참조 이미지 MIME 타입
    # 캐릭터 컨텍스트 (참조 이미지 사용 시 Gemini 프롬프트에 포함)
    character_name: str | None = None  # 캐릭터 이름 (예: 페티)
    character_category: str | None = None  # 폐기물 카테고리 (예: 무색페트병)


@dataclass
class GenerateImageOutput:
    """Command 출력 DTO."""

    success: bool
    image_url: str | None = None
    description: str | None = None
    revised_prompt: str | None = None
    error_message: str | None = None
    events: list[str] = field(default_factory=list)
    # 이미지 메타데이터
    width: int | None = None
    height: int | None = None
    has_synthid: bool = False


class GenerateImageCommand:
    """이미지 생성 Command (UseCase).

    Responses API의 네이티브 image_generation tool을 사용하여
    이미지를 생성합니다.

    플로우:
    1. 프롬프트 검증
    2. 프롬프트 빌드 (캐릭터 컨텍스트 반영)
    3. ImageGeneratorPort 호출 (Responses API)
    4. 결과 반환 (이미지 URL + 설명)

    Port 주입:
    - image_generator: ImageGeneratorPort 구현체
    - prompt_loader: PromptLoaderPort 구현체 (선택)
    """

    def __init__(
        self,
        image_generator: "ImageGeneratorPort",
        prompt_loader: "PromptLoaderPort | None" = None,
    ) -> None:
        """Command 초기화.

        Args:
            image_generator: 이미지 생성 클라이언트
            prompt_loader: 프롬프트 로더 (선택, 없으면 기본 프롬프트 사용)
        """
        self._image_generator = image_generator

        # 프롬프트 로드 (optional - 없으면 기본값 사용)
        if prompt_loader:
            try:
                self._system_prompt = prompt_loader.load("image_generation", "system")
                self._character_reference_prompt = prompt_loader.load(
                    "image_generation", "character_reference"
                )
                self._reference_only_prompt = prompt_loader.load(
                    "image_generation", "reference_only"
                )
                self._basic_prompt = prompt_loader.load("image_generation", "basic")
                self._prompts_loaded = True
                logger.info("Image generation prompts loaded from files")
            except FileNotFoundError as e:
                logger.warning(f"Failed to load image generation prompts: {e}")
                self._prompts_loaded = False
                self._system_prompt = None
        else:
            self._prompts_loaded = False
            self._system_prompt = None

    def _build_generation_prompt(
        self,
        user_prompt: str,
        character_name: str | None = None,
        character_category: str | None = None,
        has_reference: bool = False,
    ) -> str:
        """이미지 생성 프롬프트 빌드.

        Args:
            user_prompt: 사용자 원본 프롬프트
            character_name: 캐릭터 이름 (예: 페티)
            character_category: 폐기물 카테고리 (예: 무색페트병)
            has_reference: 참조 이미지 여부

        Returns:
            빌드된 프롬프트 (시스템 지시 + 사용자 요청)
        """
        if not self._prompts_loaded:
            # 프롬프트 파일이 없으면 원본 프롬프트 그대로 반환
            return user_prompt

        # 시스템 프롬프트 (캐릭터 보존 강조)
        system_part = self._system_prompt + "\n\n" if self._system_prompt else ""

        if has_reference and character_name:
            # 캐릭터 정보가 있는 참조 이미지 생성
            task_prompt = self._character_reference_prompt.format(
                character_name=character_name,
                character_category=character_category or "분리배출",
                prompt=user_prompt,
            )
        elif has_reference:
            # 캐릭터 정보 없이 참조 이미지만 있는 경우
            task_prompt = self._reference_only_prompt.format(prompt=user_prompt)
        else:
            # 기본 이미지 생성
            task_prompt = self._basic_prompt.format(prompt=user_prompt)

        return system_part + task_prompt

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

        # 2. 프롬프트 빌드 (캐릭터 컨텍스트 반영)
        has_reference = input_dto.reference_image_url is not None
        built_prompt = self._build_generation_prompt(
            user_prompt=input_dto.prompt,
            character_name=input_dto.character_name,
            character_category=input_dto.character_category,
            has_reference=has_reference,
        )

        # 3. 이미지 생성 API 호출
        try:
            logger.info(
                "Generating image",
                extra={
                    "job_id": input_dto.job_id,
                    "original_prompt_length": len(input_dto.prompt),
                    "built_prompt_length": len(built_prompt),
                    "size": input_dto.size,
                    "quality": input_dto.quality,
                    "has_reference": has_reference,
                    "reference_url": input_dto.reference_image_url,
                    "character_name": input_dto.character_name,
                    "character_category": input_dto.character_category,
                    "prompts_loaded": self._prompts_loaded,
                },
            )

            if has_reference and self._image_generator.supports_reference_images:
                # 참조 이미지가 있고 지원되면 generate_with_reference 사용
                # URL만 전달 - Gemini generator에서 lazy fetch
                from chat_worker.application.ports.image_generator import ReferenceImage

                reference = ReferenceImage(
                    image_url=input_dto.reference_image_url,
                    mime_type=input_dto.reference_image_mime,
                )
                result = await self._image_generator.generate_with_reference(
                    prompt=built_prompt,
                    reference_images=[reference],
                    size=input_dto.size,
                    quality=input_dto.quality,
                )
                events.append("image_generated_with_reference")
            else:
                # 참조 이미지 없거나 미지원 시 기본 생성
                result = await self._image_generator.generate(
                    prompt=built_prompt,
                    size=input_dto.size,
                    quality=input_dto.quality,
                )
                events.append("image_generated")

            logger.info(
                "Image generation completed",
                extra={
                    "job_id": input_dto.job_id,
                    "has_description": result.description is not None,
                    "used_reference": has_reference
                    and self._image_generator.supports_reference_images,
                },
            )

            return GenerateImageOutput(
                success=True,
                image_url=result.image_url,
                description=result.description,
                revised_prompt=result.revised_prompt,
                events=events,
                width=result.width,
                height=result.height,
                has_synthid=result.has_synthid,
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
