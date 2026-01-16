"""Vision Service - 순수 비즈니스 로직.

Port 의존 없이 순수 로직만 담당:
- 분류 결과 검증
- 컨텍스트 변환 (to_answer_context)
- 에러 컨텍스트 생성

Port 호출(Vision API)은 Command에서 담당.

Clean Architecture:
- Service: 이 파일 (순수 로직, Port 의존 없음)
- Command: AnalyzeImageCommand (Port 호출, 오케스트레이션)
- Port: VisionModelPort (Vision API 호출)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class VisionService:
    """Vision 비즈니스 로직 서비스 (순수 로직).

    Port 의존 없이 순수 비즈니스 로직만 담당:
    - 분류 결과 검증
    - 컨텍스트 변환
    - 에러 처리

    Vision API 호출은 Command에서 담당.
    """

    @staticmethod
    def validate_result(result: dict[str, Any] | None) -> bool:
        """분류 결과 유효성 검증.

        Args:
            result: Vision API 응답

        Returns:
            유효 여부
        """
        if not result:
            return False

        classification = result.get("classification")
        if not classification:
            return False

        # major_category는 필수
        return bool(classification.get("major_category"))

    @staticmethod
    def to_answer_context(
        result: dict[str, Any],
        image_url: str,
    ) -> dict[str, Any]:
        """Answer 노드용 컨텍스트 생성.

        Args:
            result: Vision API 분류 결과
            image_url: 분석한 이미지 URL

        Returns:
            Answer 노드용 컨텍스트 딕셔너리
        """
        classification = result.get("classification", {})
        situation_tags = result.get("situation_tags", [])
        confidence = result.get("confidence", 0.0)

        context: dict[str, Any] = {
            "analyzed": True,
            "image_url": image_url,
            "classification": {
                "major": classification.get("major_category", "알 수 없음"),
                "middle": classification.get("middle_category"),
                "minor": classification.get("minor_category"),
            },
            "confidence": confidence,
        }

        if situation_tags:
            context["situation_tags"] = situation_tags
            context["disposal_tips"] = VisionService._generate_tips(situation_tags)

        return context

    @staticmethod
    def _generate_tips(situation_tags: list[str]) -> list[str]:
        """상황 태그에 따른 분리배출 팁 생성.

        Args:
            situation_tags: 상황 태그 목록

        Returns:
            분리배출 팁 목록
        """
        tips = []
        tag_tips = {
            "세척필요": "내용물을 비우고 깨끗이 헹궈주세요.",
            "라벨제거필요": "라벨을 제거해주세요.",
            "압축필요": "부피를 줄여서 배출해주세요.",
            "분리필요": "재질별로 분리해서 배출해주세요.",
            "뚜껑분리": "뚜껑은 따로 분리해서 배출해주세요.",
        }

        for tag in situation_tags:
            if tag in tag_tips:
                tips.append(tag_tips[tag])

        return tips

    @staticmethod
    def build_no_image_context() -> dict[str, Any]:
        """이미지 없음 컨텍스트 생성.

        Returns:
            이미지 없음 컨텍스트
        """
        return {
            "analyzed": False,
            "skipped": True,
            "reason": "no_image",
        }

    @staticmethod
    def build_error_context(error_message: str) -> dict[str, Any]:
        """에러 컨텍스트 생성.

        Args:
            error_message: 에러 메시지

        Returns:
            에러 컨텍스트
        """
        return {
            "analyzed": False,
            "error": True,
            "message": error_message,
        }

    @staticmethod
    def extract_category_for_rag(result: dict[str, Any]) -> str | None:
        """RAG 검색용 카테고리 추출.

        Vision 분류 결과에서 RAG 검색에 사용할 카테고리를 추출합니다.

        Args:
            result: Vision API 분류 결과

        Returns:
            검색용 카테고리 문자열 또는 None
        """
        classification = result.get("classification", {})

        # minor -> middle -> major 순으로 가장 구체적인 카테고리 반환
        return (
            classification.get("minor_category")
            or classification.get("middle_category")
            or classification.get("major_category")
        )
