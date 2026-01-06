"""Waste Category Enum."""

from enum import Enum


class WasteCategory(str, Enum):
    """폐기물 대분류 카테고리.

    보상 조건: 재활용폐기물(RECYCLABLE)만 리워드 대상.
    """

    RECYCLABLE = "재활용폐기물"
    GENERAL = "일반폐기물"
    BULKY = "대형폐기물"
    FOOD = "음식물폐기물"
    HAZARDOUS = "유해폐기물"
    OTHER = "기타"

    @classmethod
    def is_rewardable(cls, category: str) -> bool:
        """리워드 대상 카테고리인지 확인."""
        return category == cls.RECYCLABLE.value
