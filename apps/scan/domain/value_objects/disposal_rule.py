"""Disposal Rule Value Object."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DisposalRule:
    """배출 규정 Value Object.

    RAG 검색 결과로 반환되는 배출 규정 정보.

    Attributes:
        major_category: 대분류
        middle_category: 중분류
        minor_category: 소분류 (optional)
        disposal_method: 배출 방법
        notes: 추가 안내사항
        exceptions: 예외 사항 목록
    """

    major_category: str
    middle_category: str
    minor_category: str | None = None
    disposal_method: str = ""
    notes: str = ""
    exceptions: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DisposalRule | None:
        """딕셔너리에서 DisposalRule 생성.

        Args:
            data: RAG 검색 결과 딕셔너리

        Returns:
            DisposalRule 또는 None (데이터가 없는 경우)
        """
        if not data:
            return None

        return cls(
            major_category=data.get("major_category", ""),
            middle_category=data.get("middle_category", ""),
            minor_category=data.get("minor_category"),
            disposal_method=data.get("disposal_method", ""),
            notes=data.get("notes", ""),
            exceptions=tuple(data.get("exceptions", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환."""
        return {
            "major_category": self.major_category,
            "middle_category": self.middle_category,
            "minor_category": self.minor_category,
            "disposal_method": self.disposal_method,
            "notes": self.notes,
            "exceptions": list(self.exceptions),
        }
