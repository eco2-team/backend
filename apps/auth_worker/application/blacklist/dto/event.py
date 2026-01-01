"""Blacklist Event DTO.

RabbitMQ에서 수신하는 블랙리스트 이벤트 데이터 구조입니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class BlacklistEvent:
    """블랙리스트 이벤트 DTO.

    Attributes:
        type: 이벤트 타입 (add, remove)
        jti: JWT Token ID
        expires_at: 토큰 만료 시간
        timestamp: 이벤트 발생 시간
        user_id: 사용자 ID (optional)
        reason: 블랙리스트 사유 (optional)
    """

    type: str
    jti: str
    expires_at: datetime
    timestamp: datetime
    user_id: str | None = None
    reason: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BlacklistEvent:
        """딕셔너리에서 BlacklistEvent 생성.

        Args:
            data: 이벤트 데이터 딕셔너리

        Returns:
            BlacklistEvent 인스턴스
        """
        return cls(
            type=data["type"],
            jti=data["jti"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            user_id=data.get("user_id"),
            reason=data.get("reason"),
        )

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환."""
        return {
            "type": self.type,
            "jti": self.jti,
            "expires_at": self.expires_at.isoformat(),
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id,
            "reason": self.reason,
        }
