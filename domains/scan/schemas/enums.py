"""Scan service enumerations."""

from enum import Enum


class TaskStatus(str, Enum):
    """Scan task status values."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
