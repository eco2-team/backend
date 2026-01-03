"""Character ORM Models.

String 타입 전략 (PostgreSQL):
- VARCHAR(n): 식별자, 표준 규격 (code, character_code)
- TEXT: 기본 (Unbounded String) - name, type_label, match_label, source
- ENUM: 고정 값 집합

멱등성: (user_id, character_code) UNIQUE - users.user_characters와 통일

Ref: https://rooftopsnow.tistory.com/132
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from domains._shared.database.base import Base


class CharacterModel(Base):
    """캐릭터 ORM 모델.

    character.characters 테이블에 매핑됩니다.
    """

    __tablename__ = "characters"
    __table_args__ = {"schema": "character"}

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    # 식별자: VARCHAR (표준 길이 제한)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # CSV 동적 값: TEXT (Unbounded String 전략)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    type_label: Mapped[str] = mapped_column(Text, nullable=False)
    dialog: Mapped[str] = mapped_column(Text, nullable=False)
    match_label: Mapped[str | None] = mapped_column(Text, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    ownerships: Mapped[list["CharacterOwnershipModel"]] = relationship(
        "CharacterOwnershipModel",
        back_populates="character",
        lazy="noload",
    )


class CharacterOwnershipModel(Base):
    """캐릭터 소유권 ORM 모델.

    character.character_ownerships 테이블에 매핑됩니다.

    멱등성: (user_id, character_code) UNIQUE - users.user_characters와 통일
    """

    __tablename__ = "character_ownerships"
    __table_args__ = (
        # character_code 기준 멱등성 (users.user_characters와 통일)
        UniqueConstraint("user_id", "character_code", name="uq_character_ownership_user_code"),
        {"schema": "character"},
    )

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    character_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("character.characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 식별자: VARCHAR (표준 길이 제한, character.code와 동일)
    character_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 확장 가능: TEXT (scan, default-onboard, trade, 추후 추가 가능)
    source: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="owned")
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    character: Mapped[CharacterModel] = relationship(
        "CharacterModel",
        back_populates="ownerships",
        lazy="joined",
    )
