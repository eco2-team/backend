"""Prompt Repository Port - 프롬프트/리소스 로딩 추상화."""

from abc import ABC, abstractmethod
from typing import Any


class PromptRepositoryPort(ABC):
    """프롬프트 리포지토리 포트 - 리소스 접근 추상화.

    파일 시스템, S3, ConfigMap 등 다양한 구현체를 DI로 주입.
    """

    @abstractmethod
    def get_prompt(self, name: str) -> str:
        """프롬프트 템플릿 로딩.

        Args:
            name: 프롬프트 이름 (확장자 제외)
                - "vision_classification_prompt"
                - "answer_generation_prompt"
                - "text_classification_prompt"

        Returns:
            프롬프트 템플릿 문자열
        """
        pass

    @abstractmethod
    def get_classification_schema(self) -> dict[str, Any]:
        """분류체계 YAML 로딩.

        Returns:
            item_class_list.yaml 내용 (dict)
        """
        pass

    @abstractmethod
    def get_situation_tags(self) -> dict[str, Any]:
        """상황 태그 YAML 로딩.

        Returns:
            situation_tags.yaml 내용 (dict)
        """
        pass
