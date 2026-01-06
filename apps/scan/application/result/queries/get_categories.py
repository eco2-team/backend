"""Get Categories Query - 카테고리 목록 조회.

Note:
    카테고리 목록은 정적 데이터이므로 외부 저장소 의존성 없이 상수로 관리합니다.
    실제 RAG (배출 규정 검색)는 scan_worker에서 수행합니다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScanCategory:
    """스캔 카테고리 DTO."""

    id: int
    name: str
    display_name: str
    instructions: list[str]


# 정적 카테고리 목록 (scan_worker의 RAG와 무관)
_CATEGORIES = [
    ScanCategory(
        id=1,
        name="recyclable",
        display_name="재활용폐기물",
        instructions=["내용물을 비우고 헹굽니다", "라벨을 제거합니다", "재질별로 분리합니다"],
    ),
    ScanCategory(
        id=2,
        name="general",
        display_name="일반폐기물",
        instructions=["종량제 봉투에 담습니다", "음식물이 묻지 않도록 합니다"],
    ),
    ScanCategory(
        id=3,
        name="food",
        display_name="음식물폐기물",
        instructions=["물기를 제거합니다", "음식물 전용 봉투에 담습니다"],
    ),
    ScanCategory(
        id=4,
        name="bulky",
        display_name="대형폐기물",
        instructions=["구청에 수거 신청합니다", "스티커를 부착합니다"],
    ),
]


class GetCategoriesQuery:
    """카테고리 목록 조회 Query."""

    def execute(self) -> list[ScanCategory]:
        """카테고리 목록 조회 실행.

        Returns:
            카테고리 목록 (정적 데이터)
        """
        return _CATEGORIES
