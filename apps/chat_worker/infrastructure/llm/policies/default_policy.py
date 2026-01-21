"""Default LLM Policy - LLMPolicyPort 구현체.

기본 정책 구현:
- 작업 타입별 모델 선택
- 프롬프트 템플릿 관리
- 리트라이 정책

Port: application/ports/llm/llm_policy.py
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable, TypeVar

from chat_worker.application.ports.llm import (
    LLMPolicyPort,
    ModelTier,
    TaskType,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 작업 타입별 추천 모델
TASK_MODEL_MAP = {
    TaskType.INTENT_CLASSIFICATION: {
        ModelTier.FAST: "gpt-5.2-instant",
        ModelTier.STANDARD: "gpt-5.2",
        ModelTier.PREMIUM: "gpt-5.2-pro",
    },
    TaskType.ANSWER_GENERATION: {
        ModelTier.FAST: "gemini-3-flash-preview",
        ModelTier.STANDARD: "gpt-5.2",
        ModelTier.PREMIUM: "gpt-5.2-pro",
    },
    TaskType.SUMMARIZATION: {
        ModelTier.FAST: "gemini-3-flash-preview",
        ModelTier.STANDARD: "gemini-3-pro-preview",
        ModelTier.PREMIUM: "gpt-5.2-pro",
    },
}


class DefaultLLMPolicy(LLMPolicyPort):
    """기본 LLM 정책.

    모델 선택, 프롬프트 템플릿, 리트라이 정책 관리.
    """

    def __init__(
        self,
        prompts_path: str | Path | None = None,
    ):
        """초기화.

        Args:
            prompts_path: 프롬프트 템플릿 경로
        """
        if prompts_path is None:
            self._prompts_path = Path(__file__).parent.parent.parent / "assets" / "prompts"
        else:
            self._prompts_path = Path(prompts_path)

        self._templates: dict[str, str] = {}
        self._load_templates()

    def _load_templates(self) -> None:
        """프롬프트 템플릿 로드."""
        if not self._prompts_path.exists():
            logger.warning(
                "Prompts path not found",
                extra={"path": str(self._prompts_path)},
            )
            return

        for template_file in self._prompts_path.glob("*.txt"):
            try:
                with open(template_file, encoding="utf-8") as f:
                    template_name = template_file.stem
                    self._templates[template_name] = f.read()
                    logger.debug(
                        "Template loaded",
                        extra={"template_name": template_name},
                    )
            except Exception as e:
                logger.error(
                    "Failed to load template",
                    extra={"file": str(template_file), "error": str(e)},
                )

    def select_model(
        self,
        task_type: TaskType,
        preferred_tier: ModelTier = ModelTier.STANDARD,
    ) -> str:
        """작업 타입에 따른 모델 선택."""
        task_models = TASK_MODEL_MAP.get(task_type)
        if not task_models:
            logger.warning(
                "Unknown task type, using default model",
                extra={"task_type": task_type.value},
            )
            return "gpt-5.2"

        return task_models.get(preferred_tier, task_models[ModelTier.STANDARD])

    def format_prompt(
        self,
        template_name: str,
        **kwargs: Any,
    ) -> str:
        """프롬프트 템플릿 포매팅."""
        template = self._templates.get(template_name)
        if not template:
            logger.warning(
                "Template not found",
                extra={"template_name": template_name},
            )
            return ""

        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.error(
                "Template formatting failed",
                extra={"template_name": template_name, "error": str(e)},
            )
            return template

    async def execute_with_retry(
        self,
        operation: Callable[[], T],
        max_retries: int = 3,
        backoff_factor: float = 1.5,
    ) -> T:
        """리트라이 정책 적용."""
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                return await operation() if asyncio.iscoroutinefunction(operation) else operation()  # type: ignore
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    delay = backoff_factor**attempt
                    logger.warning(
                        "Operation failed, retrying",
                        extra={
                            "attempt": attempt + 1,
                            "max_retries": max_retries,
                            "delay": delay,
                            "error": str(e),
                        },
                    )
                    await asyncio.sleep(delay)

        raise last_error  # type: ignore

    async def check_rate_limit(
        self,
        model: str,
    ) -> bool:
        """레이트리밋 확인.

        현재는 항상 True 반환 (향후 Redis 기반 구현 가능).
        """
        # TODO: Redis 기반 레이트리밋 구현
        return True
