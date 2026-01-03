from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from domains.character.database.base import Base
from domains.character.enums import CharacterOwnershipStatus


class Character(Base):
    """Static definition of a collectible character.

    String 타입 전략 (PostgreSQL):
    - VARCHAR(n): 식별자, 표준 규격 (code)
    - TEXT: 기본 (Unbounded String) - name, type_label, match_label
    - ENUM: 고정 값 집합 (해당 없음, CSV 동적 값)

    Ref: https://rooftopsnow.tistory.com/132
    """

    __tablename__ = "characters"
    __table_args__ = {"schema": "character"}

    id: Mapped[UUID] = mapped_column(
        default=uuid4,
        primary_key=True,
    )
    # 식별자: VARCHAR (표준 길이 제한)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # CSV 동적 값: TEXT (Unbounded String 전략)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    type_label: Mapped[str] = mapped_column(Text, nullable=False)
    dialog: Mapped[str] = mapped_column(Text, nullable=False)
    match_label: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    ownerships: Mapped[list["CharacterOwnership"]] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
    )


class CharacterOwnership(Base):
    """Tracks the current ownership state of a character for a user.

    String 타입 전략 (PostgreSQL):
    - VARCHAR(n): 식별자 (character_code)
    - TEXT: 기본 (source) - 확장 가능성 고려
    - ENUM: 고정 값 (status: owned, burned, traded)

    멱등성: (user_id, character_code) UNIQUE - users.user_characters와 통일
    Ref: https://rooftopsnow.tistory.com/132
    """

    __tablename__ = "character_ownerships"
    __table_args__ = (
        # character_code 기준 멱등성 (users.user_characters와 통일)
        UniqueConstraint("user_id", "character_code", name="uq_character_ownership_user_code"),
        {"schema": "character"},
    )

    id: Mapped[UUID] = mapped_column(default=uuid4, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    character_id: Mapped[UUID] = mapped_column(
        ForeignKey(Character.id, ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 식별자: VARCHAR (표준 길이 제한, character.code와 동일)
    character_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 확장 가능: TEXT (scan, default-onboard, trade, 추후 추가 가능)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 고정 값: ENUM (owned, burned, traded)
    status: Mapped[CharacterOwnershipStatus] = mapped_column(
        SqlEnum(CharacterOwnershipStatus, name="character_ownership_status", native_enum=False),
        nullable=False,
        default=CharacterOwnershipStatus.OWNED,
    )
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

    character: Mapped[Character] = relationship(back_populates="ownerships", lazy="joined")
