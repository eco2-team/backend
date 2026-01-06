"""Get Categories Query - 카테고리 목록 조회."""

from __future__ import annotations

from dataclasses import dataclass

from apps.scan.application.pipeline.ports import RuleRepository


@dataclass
class ScanCategory:
    """스캔 카테고리 DTO."""

    id: int
    name: str
    display_name: str
    instructions: list[str]


class GetCategoriesQuery:
    """카테고리 목록 조회 Query."""

    def __init__(self, rule_repository: RuleRepository):
        """초기화.

        Args:
            rule_repository: 배출 규정 저장소
        """
        self._rule_repository = rule_repository

    def execute(self) -> list[ScanCategory]:
        """카테고리 목록 조회 실행.

        Returns:
            카테고리 목록
        """
        raw_categories = self._rule_repository.get_all_categories()

        return [
            ScanCategory(
                id=cat.get("id", 0),
                name=cat.get("name", ""),
                display_name=cat.get("display_name", ""),
                instructions=cat.get("instructions", []),
            )
            for cat in raw_categories
        ]
