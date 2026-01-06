"""Classification Value Object."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scan.domain.enums import WasteCategory


@dataclass(frozen=True, slots=True)
class Classification:
    """Vision 분류 결과 Value Object.

    Attributes:
        major_category: 대분류 (예: 재활용폐기물)
        middle_category: 중분류 (예: 플라스틱)
        minor_category: 소분류 (예: PET, optional)
        situation_tags: 상황 태그 목록
        confidence: 신뢰도 (0.0 ~ 1.0, optional)
    """

    major_category: str
    middle_category: str
    minor_category: str | None = None
    situation_tags: tuple[str, ...] = ()
    confidence: float | None = None

    @property
    def is_rewardable(self) -> bool:
        """리워드 대상인지 확인.

        조건: 대분류가 '재활용폐기물'이고 중분류가 있어야 함.
        """
        return WasteCategory.is_rewardable(self.major_category) and bool(
            self.middle_category.strip()
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Classification:
        """딕셔너리에서 Classification 생성.

        Args:
            data: Vision API 응답 형식의 딕셔너리
                {
                    "classification": {
                        "major_category": "...",
                        "middle_category": "...",
                        "minor_category": "..."
                    },
                    "situation_tags": ["..."],
                    "meta": {...}
                }
        """
        classification = data.get("classification", {})
        return cls(
            major_category=classification.get("major_category", ""),
            middle_category=classification.get("middle_category", ""),
            minor_category=classification.get("minor_category"),
            situation_tags=tuple(data.get("situation_tags", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환 (API 응답용)."""
        return {
            "classification": {
                "major_category": self.major_category,
                "middle_category": self.middle_category,
                "minor_category": self.minor_category,
            },
            "situation_tags": list(self.situation_tags),
        }
