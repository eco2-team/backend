"""Vision Step - 이미지 분류 단계.

Stage 1: GPT Vision을 사용한 이미지 분류.
VisionModelPort와 PromptRepositoryPort만 의존.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import yaml

from scan_worker.application.classify.ports.prompt_repository import (
    PromptRepositoryPort,
)
from scan_worker.application.classify.ports.vision_model import VisionModelPort
from scan_worker.application.common.step_interface import Step

if TYPE_CHECKING:
    from scan_worker.application.classify.dto.classify_context import (
        ClassifyContext,
    )

logger = logging.getLogger(__name__)


class VisionStep(Step):
    """Vision 분석 Step - VisionModelPort만 의존.

    이미지 분석 후 분류 결과를 Context에 저장.
    progress: 0 → 25
    """

    def __init__(
        self,
        vision_model: VisionModelPort,
        prompt_repository: PromptRepositoryPort,
    ):
        """초기화.

        Args:
            vision_model: Vision 모델 Port
            prompt_repository: 프롬프트 리포지토리 Port
        """
        self._vision = vision_model
        self._prompts = prompt_repository

    def run(self, ctx: "ClassifyContext") -> "ClassifyContext":
        """Step 실행.

        Args:
            ctx: 입력 Context

        Returns:
            업데이트된 Context (classification 필드 채워짐)
        """
        start = time.perf_counter()

        logger.info(
            "VisionStep started",
            extra={"task_id": ctx.task_id, "user_id": ctx.user_id},
        )

        # 1. 프롬프트 로딩 (Port 통해 추상화)
        prompt_template = self._prompts.get_prompt("vision_classification_prompt")
        schema = self._prompts.get_classification_schema()
        tags = self._prompts.get_situation_tags()

        # 2. 프롬프트 렌더링 (순수 로직)
        prompt = self._render_prompt(prompt_template, schema, tags, ctx.user_input)

        # 3. Vision 모델 호출 (Port 통해 추상화)
        result = self._vision.analyze_image(
            prompt=prompt,
            image_url=ctx.image_url,
            user_input=ctx.user_input,
        )

        elapsed = (time.perf_counter() - start) * 1000

        # 4. Context 업데이트
        ctx.classification = result
        ctx.latencies["duration_vision_ms"] = elapsed
        ctx.progress = 25

        logger.info(
            "VisionStep completed",
            extra={
                "task_id": ctx.task_id,
                "elapsed_ms": elapsed,
                "major_category": result.get("classification", {}).get("major_category"),
            },
        )

        return ctx

    def _render_prompt(
        self,
        template: str,
        schema: dict,
        tags: dict,
        user_input: str | None,
    ) -> str:
        """프롬프트 렌더링 (순수 함수).

        Args:
            template: 프롬프트 템플릿
            schema: 분류체계 YAML
            tags: 상황 태그 YAML
            user_input: 사용자 입력

        Returns:
            렌더링된 프롬프트
        """
        # YAML을 문자열로 변환
        schema_text = yaml.dump(schema, allow_unicode=True)
        tags_text = yaml.dump(tags, allow_unicode=True)

        # 템플릿 치환
        prompt = template.replace("{{ITEM_CLASS_YAML}}", schema_text)
        prompt = prompt.replace("{{SITUATION_TAG_YAML}}", tags_text)

        return prompt
