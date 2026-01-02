"""LoginAudit Entity.

로그인 감사 기록을 나타내는 엔티티입니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class LoginAudit:
    """로그인 감사 엔티티.

    Attributes:
        id: 감사 기록 고유 식별자
        user_id: 사용자 ID
        provider: OAuth 프로바이더
        jti: JWT Token ID
        login_ip: 로그인 IP 주소 (선택)
        user_agent: User-Agent 헤더 (선택)
        issued_at: 발급 시각
    """

    id: UUID
    user_id: UUID
    provider: str
    jti: str
    issued_at: datetime
    login_ip: str | None = None
    user_agent: str | None = None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LoginAudit):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
