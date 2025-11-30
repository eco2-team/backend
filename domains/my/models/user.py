from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from domains.my.database.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "user_profile"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    auth_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        unique=True,
        index=True,
    )
    username: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    nickname: Mapped[str | None] = mapped_column(String(120), nullable=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    profile_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
