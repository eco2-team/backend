"""Analyze Image Command.

이미지 분석 및 폐기물 분류 UseCase.

Clean Architecture:
- Command(UseCase): 이 파일 - Port 호출, 오케스트레이션
- Service: VisionService - 순수 비즈니스 로직 (결과 검증, 컨텍스트 변환)
- Port: VisionModelPort - Vision API 호출
- Node(Adapter): vision_node.py - LangGraph glue

구조:
- Command: 이미지 검증, Vision API 호출, Service 호출, 오케스트레이션
- Service: 결과 검증, 컨텍스트 변환 (Port 의존 없음)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from chat_worker.application.services.vision_service import VisionService

if TYPE_CHECKING:
    from chat_worker.application.ports.vision import VisionModelPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnalyzeImageInput:
    """Command 입력 DTO."""

    job_id: str
    image_url: str | None = None
    message: str = ""  # 사용자 추가 설명


@dataclass
class AnalyzeImageOutput:
    """Command 출력 DTO."""

    success: bool
    classification_result: dict[str, Any] | None = None
    has_image: bool = False
    skipped: bool = False  # 이미지 없어서 스킵됨
    error_message: str | None = None
    events: list[str] = field(default_factory=list)


class AnalyzeImageCommand:
    """이미지 분석 Command (UseCase).

    Port 호출 + 오케스트레이션:
    1. 이미지 URL 검증
    2. Vision API 호출 (VisionModelPort)
    3. 결과 검증 및 컨텍스트 변환 (Service - 순수 로직)

    Port 주입:
    - vision_model: Vision API 클라이언트
    """

    def __init__(
        self,
        vision_model: "VisionModelPort",
    ) -> None:
        """Command 초기화.

        Args:
            vision_model: Vision 모델 클라이언트
        """
        self._vision_model = vision_model

    async def execute(self, input_dto: AnalyzeImageInput) -> AnalyzeImageOutput:
        """Command 실행.

        Args:
            input_dto: 입력 DTO

        Returns:
            출력 DTO
        """
        events: list[str] = []

        # 1. 이미지 URL 검증
        if not input_dto.image_url:
            events.append("no_image_skipped")
            logger.debug(
                "No image_url, skipping vision analysis",
                extra={"job_id": input_dto.job_id},
            )
            return AnalyzeImageOutput(
                success=True,
                classification_result=VisionService.build_no_image_context(),
                has_image=False,
                skipped=True,
                events=events,
            )

        events.append("image_url_validated")

        # 2. Vision API 호출 (Command에서 Port 호출)
        try:
            result = await self._vision_model.analyze_image(
                image_url=input_dto.image_url,
                user_input=input_dto.message if input_dto.message else None,
            )
            events.append("vision_api_called")

            logger.info(
                "Vision analysis completed",
                extra={
                    "job_id": input_dto.job_id,
                    "major_category": result.get("classification", {}).get(
                        "major_category", "unknown"
                    ),
                },
            )

        except Exception as e:
            logger.error(
                "Vision API call failed",
                extra={"job_id": input_dto.job_id, "error": str(e)},
            )
            events.append("vision_api_error")
            return AnalyzeImageOutput(
                success=False,
                classification_result=VisionService.build_error_context(str(e)),
                has_image=True,
                error_message="이미지 분석에 실패했어요.",
                events=events,
            )

        # 3. 결과 검증 (Service - 순수 로직)
        if not VisionService.validate_result(result):
            events.append("vision_result_invalid")
            return AnalyzeImageOutput(
                success=False,
                classification_result=VisionService.build_error_context(
                    "분류 결과를 확인할 수 없어요."
                ),
                has_image=True,
                error_message="이미지에서 폐기물을 인식하지 못했어요.",
                events=events,
            )

        events.append("vision_result_valid")

        # 4. 컨텍스트 변환 (Service - 순수 로직)
        context = VisionService.to_answer_context(
            result=result,
            image_url=input_dto.image_url,
        )

        return AnalyzeImageOutput(
            success=True,
            classification_result=context,
            has_image=True,
            events=events,
        )
