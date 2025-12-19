"""Tests for ScanTaskRepository."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from domains.scan.models.scan_task import ScanTask as ScanTaskModel
from domains.scan.repositories.scan_task_repository import ScanTaskRepository
from domains.scan.schemas.enums import TaskStatus


class TestScanTaskRepository:
    """Unit tests for ScanTaskRepository."""

    def test_create_task(self):
        """Test creating a new scan task."""

        async def _test():
            mock_session = AsyncMock()
            mock_session.add = MagicMock()
            mock_session.commit = AsyncMock()
            mock_session.refresh = AsyncMock()

            repo = ScanTaskRepository(mock_session)
            task_id = uuid4()
            user_id = uuid4()

            await repo.create(
                task_id=task_id,
                user_id=user_id,
                image_url="https://example.com/image.jpg",
                user_input="테스트 질문",
            )

            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()
            mock_session.refresh.assert_called_once()

            added_task = mock_session.add.call_args[0][0]
            assert added_task.id == task_id
            assert added_task.user_id == user_id
            assert added_task.status == TaskStatus.PENDING
            assert added_task.image_url == "https://example.com/image.jpg"

        asyncio.run(_test())

    def test_get_by_id_found(self):
        """Test retrieving an existing task."""

        async def _test():
            mock_session = AsyncMock()
            task_id = uuid4()
            mock_task = ScanTaskModel(
                id=task_id,
                user_id=uuid4(),
                status=TaskStatus.COMPLETED,
            )

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_task
            mock_session.execute = AsyncMock(return_value=mock_result)

            repo = ScanTaskRepository(mock_session)
            result = await repo.get_by_id(task_id)

            assert result is not None
            assert result.id == task_id
            assert result.status == TaskStatus.COMPLETED

        asyncio.run(_test())

    def test_get_by_id_not_found(self):
        """Test retrieving a non-existent task."""

        async def _test():
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)

            repo = ScanTaskRepository(mock_session)
            result = await repo.get_by_id(uuid4())

            assert result is None

        asyncio.run(_test())

    def test_update_completed(self):
        """Test marking a task as completed using single UPDATE query."""

        async def _test():
            mock_session = AsyncMock()
            task_id = uuid4()

            # Mock the returned task after UPDATE ... RETURNING
            mock_task = ScanTaskModel(
                id=task_id,
                user_id=uuid4(),
                status=TaskStatus.COMPLETED,
                category="재활용폐기물",
                completed_at=datetime.now(timezone.utc),
            )

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_task
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.commit = AsyncMock()

            repo = ScanTaskRepository(mock_session)
            result = await repo.update_completed(
                task_id,
                category="재활용폐기물",
                confidence=0.95,
                pipeline_result=None,
                reward=None,
            )

            assert result is not None
            assert result.status == TaskStatus.COMPLETED
            assert result.category == "재활용폐기물"
            mock_session.execute.assert_called_once()
            mock_session.commit.assert_called_once()

        asyncio.run(_test())

    def test_update_failed(self):
        """Test marking a task as failed using single UPDATE query."""

        async def _test():
            mock_session = AsyncMock()
            task_id = uuid4()

            # Mock the returned task after UPDATE ... RETURNING
            mock_task = ScanTaskModel(
                id=task_id,
                user_id=uuid4(),
                status=TaskStatus.FAILED,
                error_message="Pipeline failed",
                completed_at=datetime.now(timezone.utc),
            )

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_task
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.commit = AsyncMock()

            repo = ScanTaskRepository(mock_session)
            result = await repo.update_failed(
                task_id,
                error_message="Pipeline failed",
            )

            assert result is not None
            assert result.status == TaskStatus.FAILED
            assert result.error_message == "Pipeline failed"
            mock_session.execute.assert_called_once()
            mock_session.commit.assert_called_once()

        asyncio.run(_test())

    def test_update_completed_not_found(self):
        """Test updating a non-existent task returns None."""

        async def _test():
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.commit = AsyncMock()

            repo = ScanTaskRepository(mock_session)
            result = await repo.update_completed(
                uuid4(),
                category="test",
                confidence=None,
                pipeline_result=None,
                reward=None,
            )

            assert result is None

        asyncio.run(_test())

    def test_count_completed(self):
        """Test counting completed tasks."""

        async def _test():
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar.return_value = 42
            mock_session.execute = AsyncMock(return_value=mock_result)

            repo = ScanTaskRepository(mock_session)
            count = await repo.count_completed()

            assert count == 42

        asyncio.run(_test())

    def test_get_last_completed_at(self):
        """Test getting the last completed timestamp."""

        async def _test():
            mock_session = AsyncMock()
            expected_time = datetime.now(timezone.utc)
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = expected_time
            mock_session.execute = AsyncMock(return_value=mock_result)

            repo = ScanTaskRepository(mock_session)
            result = await repo.get_last_completed_at()

            assert result == expected_time

        asyncio.run(_test())

    def test_get_user_history(self):
        """Test getting scan history for a user."""

        async def _test():
            mock_session = AsyncMock()
            user_id = uuid4()

            mock_tasks = [
                ScanTaskModel(id=uuid4(), user_id=user_id, status=TaskStatus.COMPLETED),
                ScanTaskModel(id=uuid4(), user_id=user_id, status=TaskStatus.FAILED),
            ]

            mock_result = MagicMock()
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = mock_tasks
            mock_result.scalars.return_value = mock_scalars
            mock_session.execute = AsyncMock(return_value=mock_result)

            repo = ScanTaskRepository(mock_session)
            result = await repo.get_user_history(user_id, limit=10, offset=0)

            assert len(result) == 2
            assert result[0].status == TaskStatus.COMPLETED
            assert result[1].status == TaskStatus.FAILED

        asyncio.run(_test())
