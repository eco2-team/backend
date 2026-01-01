"""PersistBlacklistCommand 테스트."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from apps.auth_worker.application.commands.persist_blacklist import (
    PersistBlacklistCommand,
)
from apps.auth_worker.application.common.dto.blacklist_event import BlacklistEvent
from apps.auth_worker.application.common.result import ResultStatus


class TestPersistBlacklistCommand:
    """PersistBlacklistCommand 테스트."""

    @pytest.fixture
    def command(self, mock_blacklist_store: AsyncMock) -> PersistBlacklistCommand:
        """테스트용 Command 인스턴스."""
        return PersistBlacklistCommand(mock_blacklist_store)

    @pytest.mark.asyncio
    async def test_execute_add_success(
        self,
        command: PersistBlacklistCommand,
        mock_blacklist_store: AsyncMock,
        sample_blacklist_data: dict[str, Any],
    ) -> None:
        """add 이벤트 성공 테스트."""
        event = BlacklistEvent.from_dict(sample_blacklist_data)

        result = await command.execute(event)

        assert result.status == ResultStatus.SUCCESS
        mock_blacklist_store.add.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_remove_success(
        self,
        command: PersistBlacklistCommand,
        mock_blacklist_store: AsyncMock,
        sample_blacklist_data: dict[str, Any],
    ) -> None:
        """remove 이벤트 성공 테스트."""
        sample_blacklist_data["type"] = "remove"
        event = BlacklistEvent.from_dict(sample_blacklist_data)

        result = await command.execute(event)

        assert result.status == ResultStatus.SUCCESS
        mock_blacklist_store.remove.assert_awaited_once_with(event.jti)

    @pytest.mark.asyncio
    async def test_execute_unknown_type_drops(
        self,
        command: PersistBlacklistCommand,
        sample_blacklist_data: dict[str, Any],
    ) -> None:
        """알 수 없는 타입은 DROP."""
        sample_blacklist_data["type"] = "unknown"
        event = BlacklistEvent.from_dict(sample_blacklist_data)

        result = await command.execute(event)

        assert result.status == ResultStatus.DROP
        assert "Unknown event type" in (result.message or "")

    @pytest.mark.asyncio
    async def test_execute_connection_error_retryable(
        self,
        command: PersistBlacklistCommand,
        mock_blacklist_store: AsyncMock,
        sample_blacklist_data: dict[str, Any],
    ) -> None:
        """ConnectionError는 RETRYABLE."""
        mock_blacklist_store.add.side_effect = ConnectionError("Redis down")
        event = BlacklistEvent.from_dict(sample_blacklist_data)

        result = await command.execute(event)

        assert result.status == ResultStatus.RETRYABLE
        assert "Redis down" in (result.message or "")

    @pytest.mark.asyncio
    async def test_execute_timeout_error_retryable(
        self,
        command: PersistBlacklistCommand,
        mock_blacklist_store: AsyncMock,
        sample_blacklist_data: dict[str, Any],
    ) -> None:
        """TimeoutError는 RETRYABLE."""
        mock_blacklist_store.add.side_effect = TimeoutError("Timeout")
        event = BlacklistEvent.from_dict(sample_blacklist_data)

        result = await command.execute(event)

        assert result.status == ResultStatus.RETRYABLE

    @pytest.mark.asyncio
    async def test_execute_value_error_drops(
        self,
        command: PersistBlacklistCommand,
        mock_blacklist_store: AsyncMock,
        sample_blacklist_data: dict[str, Any],
    ) -> None:
        """ValueError는 DROP."""
        mock_blacklist_store.add.side_effect = ValueError("Invalid data")
        event = BlacklistEvent.from_dict(sample_blacklist_data)

        result = await command.execute(event)

        assert result.status == ResultStatus.DROP
        assert "Invalid data" in (result.message or "")
