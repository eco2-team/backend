from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from domains.character.database.base import Base
from domains.character.enums import CharacterOwnershipStatus


class Character(Base):
    """Static definition of a collectible character."""

    __tablename__ = "characters"

    id: Mapped[UUID] = mapped_column(
        default=uuid4,
        primary_key=True,
    )
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rarity: Mapped[str] = mapped_column(String(32), nullable=False, default="common")
    element: Mapped[str | None] = mapped_column(String(32), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    match_label: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(
        "metadata", JSON, nullable=True, default=dict
    )
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
    """Tracks the current ownership state of a character for a user."""

    __tablename__ = "character_ownerships"
    __table_args__ = (
        UniqueConstraint("user_id", "character_id", name="uq_character_ownership_user_character"),
    )

    id: Mapped[UUID] = mapped_column(default=uuid4, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    character_id: Mapped[UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
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
