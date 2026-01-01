"""UserSocialAccount Entity.

ORM과 분리된 순수 도메인 엔티티입니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID


@dataclass
class UserSocialAccount:
    """소셜 계정 엔티티.

    Attributes:
        id: 소셜 계정 고유 식별자
        user_id: 연결된 사용자 ID
        provider: OAuth 프로바이더 (google, kakao, naver)
        provider_user_id: 프로바이더에서의 사용자 ID
        email: 소셜 계정 이메일 (선택)
        last_login_at: 마지막 로그인 시각 (선택)
        created_at: 생성 시각
        updated_at: 수정 시각
    """

    id: UUID
    user_id: UUID
    provider: str
    provider_user_id: str
    created_at: datetime
    updated_at: datetime
    email: str | None = None
    last_login_at: datetime | None = None

    def update_login_time(self) -> None:
        """로그인 시간 업데이트."""
        now = datetime.now(timezone.utc)
        self.last_login_at = now
        self.updated_at = now

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UserSocialAccount):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
