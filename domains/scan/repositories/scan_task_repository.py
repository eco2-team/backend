"""Repository for ScanTask persistence operations."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from domains.scan.models.scan_task import ScanTask
from domains.scan.schemas.enums import TaskStatus

if TYPE_CHECKING:
    from domains._shared.schemas.waste import WasteClassificationResult
    from domains.character.schemas.reward import CharacterRewardResponse

logger = logging.getLogger(__name__)


class ScanTaskRepository:
    """Repository for ScanTask database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        task_id: UUID,
        user_id: UUID,
        image_url: str | None = None,
        user_input: str | None = None,
    ) -> ScanTask:
        """Create a new scan task in pending status."""
        task = ScanTask(
            id=task_id,
            user_id=user_id,
            status=TaskStatus.PENDING,
            image_url=image_url,
            user_input=user_input,
        )
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        logger.debug("Created scan task", extra={"task_id": str(task_id)})
        return task

    async def get_by_id(self, task_id: UUID) -> ScanTask | None:
        """Retrieve a scan task by its ID."""
        stmt = select(ScanTask).where(ScanTask.id == task_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_processing(self, task_id: UUID) -> ScanTask | None:
        """Mark task as processing using single UPDATE query."""
        stmt = (
            update(ScanTask)
            .where(ScanTask.id == task_id)
            .values(status=TaskStatus.PROCESSING)
            .returning(ScanTask)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.scalar_one_or_none()

    async def update_completed(
        self,
        task_id: UUID,
        *,
        category: str | None,
        confidence: float | None,
        pipeline_result: WasteClassificationResult | None,
        reward: CharacterRewardResponse | None,
    ) -> ScanTask | None:
        """Mark task as completed using single UPDATE query (race-condition safe)."""
        completed_at = datetime.now(timezone.utc)

        # Convert Pydantic models to dict for JSONB storage
        pipeline_dict = pipeline_result.model_dump(mode="json") if pipeline_result else None
        reward_dict = reward.model_dump(mode="json") if reward else None

        stmt = (
            update(ScanTask)
            .where(ScanTask.id == task_id)
            .values(
                status=TaskStatus.COMPLETED,
                category=category,
                confidence=confidence,
                completed_at=completed_at,
                pipeline_result=pipeline_dict,
                reward=reward_dict,
            )
            .returning(ScanTask)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        task = result.scalar_one_or_none()
        if task:
            logger.debug("Completed scan task", extra={"task_id": str(task_id)})
        return task

    async def update_failed(
        self,
        task_id: UUID,
        *,
        error_message: str,
    ) -> ScanTask | None:
        """Mark task as failed using single UPDATE query (race-condition safe)."""
        completed_at = datetime.now(timezone.utc)

        stmt = (
            update(ScanTask)
            .where(ScanTask.id == task_id)
            .values(
                status=TaskStatus.FAILED,
                error_message=error_message,
                completed_at=completed_at,
            )
            .returning(ScanTask)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        task = result.scalar_one_or_none()
        if task:
            logger.debug(
                "Failed scan task",
                extra={"task_id": str(task_id), "error": error_message},
            )
        return task

    async def get_user_history(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ScanTask]:
        """Get scan history for a user, ordered by creation time desc."""
        stmt = (
            select(ScanTask)
            .where(ScanTask.user_id == user_id)
            .order_by(ScanTask.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_completed(self) -> int:
        """Count total completed tasks (for metrics)."""
        from sqlalchemy import func

        stmt = (
            select(func.count())
            .select_from(ScanTask)
            .where(ScanTask.status == TaskStatus.COMPLETED)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_last_completed_at(self) -> datetime | None:
        """Get timestamp of most recently completed task (for metrics)."""
        stmt = (
            select(ScanTask.completed_at)
            .where(ScanTask.status == TaskStatus.COMPLETED)
            .where(ScanTask.completed_at.isnot(None))
            .order_by(ScanTask.completed_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
