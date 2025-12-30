from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from domains.auth.infrastructure.database.base import Base

if TYPE_CHECKING:  # pragma: no cover
    from domains.auth.domain.models.user_social_account import UserSocialAccount


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", "phone_number", name="uq_auth_users_name_phone"),
        {"schema": "auth"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    username: Mapped[Optional[str]] = mapped_column(String(120))
    nickname: Mapped[Optional[str]] = mapped_column(String(120))
    profile_image_url: Mapped[Optional[str]] = mapped_column(String(512))
    phone_number: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
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
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    social_accounts: Mapped[List["UserSocialAccount"]] = relationship(
        "UserSocialAccount",
        back_populates="user",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    @property
    def primary_social_account(self):
        if not self.social_accounts:
            return None
        return max(
            self.social_accounts,
            key=lambda account: (
                account.last_login_at or account.updated_at or account.created_at,
                account.created_at,
            ),
        )

    @property
    def provider(self) -> Optional[str]:
        primary = self.primary_social_account
        return primary.provider if primary else None

    @property
    def provider_user_id(self) -> Optional[str]:
        primary = self.primary_social_account
        return primary.provider_user_id if primary else None

    @property
    def email(self) -> Optional[str]:
        primary = self.primary_social_account
        return primary.email if primary else None
