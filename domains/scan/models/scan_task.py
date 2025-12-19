"""ScanTask ORM model with CDC-friendly design."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, Float, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from domains.scan.database.base import Base
from domains.scan.schemas.enums import TaskStatus


class ScanTask(Base):
    """
    Persistent storage for scan classification tasks.

    Designed for Debezium CDC compatibility:
    - UUID primary key for Kafka partition key
    - updated_at for timestamp-based filtering
    - status column for state change tracking
    - JSONB columns for flexible result storage
    """

    __tablename__ = "scan_tasks"
    __table_args__ = (
        Index("ix_scan_tasks_user_id", "user_id"),
        Index("ix_scan_tasks_created_at", "created_at"),
        Index("ix_scan_tasks_status", "status"),
        {"schema": "scan"},
    )

    # Primary key - used as Debezium event key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Foreign key to user (no FK constraint for cross-service boundary)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    # Task status: pending -> processing -> completed/failed
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, native_enum=False, length=20),
        nullable=False,
        default=TaskStatus.PENDING,
    )

    # Classification result
    category: Mapped[Optional[str]] = mapped_column(String(100))
    confidence: Mapped[Optional[float]] = mapped_column(Float)

    # AI pipeline result (JSONB for schema flexibility)
    pipeline_result: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Character reward info (JSONB for schema flexibility)
    reward: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Input data
    image_url: Mapped[Optional[str]] = mapped_column(Text)
    user_input: Mapped[Optional[str]] = mapped_column(Text)

    # Error handling
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps - critical for CDC filtering and partitioning
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
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
    )

    def __repr__(self) -> str:
        return f"<ScanTask(id={self.id}, status={self.status}, category={self.category})>"
