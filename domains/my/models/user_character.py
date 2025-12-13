"""User character ownership model - 사용자 캐릭터 소유 정보.

이 테이블은 character.character_ownerships를 대체하여
my 도메인에서 사용자의 캐릭터 인벤토리를 독립적으로 관리합니다.

마이그레이션 계획:
1. 이 모델로 my.user_characters 테이블 생성
2. character.character_ownerships 데이터 마이그레이션
3. character → my gRPC 연동 (GrantCharacter)
4. character.character_ownerships 제거
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from domains.my.database.base import Base
from domains.my.enums import UserCharacterStatus


class UserCharacter(Base):
    """사용자의 캐릭터 소유 정보.

    character 도메인의 CharacterOwnership을 대체합니다.
    FK 없이 character_id만 저장하여 도메인 간 독립성을 보장합니다.
    """

    __tablename__ = "user_characters"
    __table_args__ = (
        UniqueConstraint("user_id", "character_id", name="uq_user_character"),
        {"schema": "user_profile"},
    )

    id: Mapped[UUID] = mapped_column(default=uuid4, primary_key=True)

    # 사용자 ID (auth.users 참조, FK 없음)
    user_id: Mapped[UUID] = mapped_column(nullable=False, index=True)

    # 캐릭터 ID (character.characters 참조, FK 없음 - 도메인 독립성)
    character_id: Mapped[UUID] = mapped_column(nullable=False, index=True)

    # 비정규화된 캐릭터 정보 (조회 최적화, character API 호출 감소)
    character_code: Mapped[str] = mapped_column(String(64), nullable=False)
    character_name: Mapped[str] = mapped_column(String(120), nullable=False)

    # 획득 경로 (scan, onboarding, event 등)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # 소유 상태
    status: Mapped[UserCharacterStatus] = mapped_column(
        String(20),
        nullable=False,
        default=UserCharacterStatus.OWNED,
    )

    # 타임스탬프
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
