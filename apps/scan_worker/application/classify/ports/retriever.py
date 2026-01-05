"""Retriever Port - 배출 규정 검색 추상화."""

from abc import ABC, abstractmethod
from typing import Any


class RetrieverPort(ABC):
    """규정 검색 포트 - RAG.

    JSON 파일 기반, 벡터 DB 기반 등 다양한 구현체를 DI로 주입.
    """

    @abstractmethod
    def get_disposal_rules(
        self,
        classification: dict[str, Any],
    ) -> dict[str, Any] | None:
        """분류 결과에 맞는 배출 규정 검색.

        Args:
            classification: Vision 분류 결과
                {
                    "classification": {
                        "major_category": "대분류",
                        "middle_category": "중분류",
                    },
                    ...
                }

        Returns:
            배출 규정 dict (매칭 실패 시 None)
        """
        pass
