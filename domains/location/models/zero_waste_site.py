from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from domains.location.database.base import Base


class ZeroWasteSite(Base):
    """ORM model mapping zero-waste shop data imported from CSV."""

    __tablename__ = "location_zero_waste_sites"
    __table_args__ = {"schema": "location"}

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    folder_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    favorite_type: Mapped[Optional[str]] = mapped_column(String(16))
    color: Mapped[Optional[int]] = mapped_column(Integer)
    memo: Mapped[Optional[str]] = mapped_column(Text)
    display1: Mapped[Optional[str]] = mapped_column(Text)
    display2: Mapped[Optional[str]] = mapped_column(Text)
    x: Mapped[Optional[float]] = mapped_column(Float)
    y: Mapped[Optional[float]] = mapped_column(Float)
    lon: Mapped[Optional[float]] = mapped_column(Float)
    lat: Mapped[Optional[float]] = mapped_column(Float)
    place_key: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

