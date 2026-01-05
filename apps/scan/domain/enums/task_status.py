"""Scan Task Status Enum."""

from enum import Enum


class TaskStatus(str, Enum):
    """스캔 작업 상태."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
