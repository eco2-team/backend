"""Outbox Event DTO.

Redis Outbox에서 읽은 이벤트 데이터 구조입니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OutboxEvent:
    """Outbox 이벤트 DTO.

    Attributes:
        raw_data: 원본 JSON 문자열
        parsed_data: 파싱된 딕셔너리 (optional)
    """

    raw_data: str
    parsed_data: dict[str, Any] | None = None

    @property
    def jti(self) -> str | None:
        """JTI 추출 (로깅용)."""
        if self.parsed_data:
            return self.parsed_data.get("jti", "")[:8]
        return None
