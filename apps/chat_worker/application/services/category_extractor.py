"""Category Extractor Service.

메시지에서 폐기물 카테고리를 추출하는 비즈니스 로직.
LLM 호출은 Command에서 조립.

Clean Architecture:
- Service: 이 파일 (순수 비즈니스 로직)
- Port: PromptLoaderPort (프롬프트 로딩 추상화)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chat_worker.application.ports.prompt_loader import PromptLoaderPort

logger = logging.getLogger(__name__)


@dataclass
class CategoryExtractionResult:
    """카테고리 추출 결과."""

    success: bool
    category: str | None = None
    error_message: str | None = None


class CategoryExtractorService:
    """폐기물 카테고리 추출 서비스 (순수 로직).

    LLM 호출은 하지 않음 - 프롬프트 구성과 결과 파싱만 담당.

    Clean Architecture:
    - 프롬프트 로딩은 PromptLoaderPort를 통해 주입받음
    - Infrastructure 직접 의존 제거
    """

    def __init__(self, prompt_loader: "PromptLoaderPort") -> None:
        """초기화.

        Args:
            prompt_loader: 프롬프트 로더 (Port 주입)
        """
        self._extraction_prompt = prompt_loader.load("extraction", "category")
        self._system_prompt = prompt_loader.load("extraction", "category_system")

    def build_extraction_prompt(self, message: str) -> str:
        """카테고리 추출 프롬프트 구성.

        Args:
            message: 사용자 메시지

        Returns:
            LLM에 전달할 프롬프트
        """
        return self._extraction_prompt.format(message=message)

    def get_system_prompt(self) -> str:
        """시스템 프롬프트 반환."""
        return self._system_prompt

    def parse_extraction_result(self, llm_response: str) -> CategoryExtractionResult:
        """LLM 응답 파싱.

        Args:
            llm_response: LLM 응답

        Returns:
            파싱된 결과
        """
        category = llm_response.strip().strip('"').strip("'")

        if not category or category.lower() == "unknown":
            return CategoryExtractionResult(
                success=False,
                error_message="폐기물 종류를 파악하지 못했어요. 좀 더 구체적으로 물어봐주세요!",
            )

        return CategoryExtractionResult(
            success=True,
            category=category,
        )
