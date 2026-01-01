"""Tests for RelayEventCommand."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from apps.auth_relay.application.commands.relay_event import RelayEventCommand
from apps.auth_relay.application.common.result import ResultStatus


class TestRelayEventCommand:
    """RelayEventCommand tests."""

    @pytest.fixture
    def command(self, mock_publisher: AsyncMock) -> RelayEventCommand:
        """Create command with mock publisher."""
        return RelayEventCommand(mock_publisher)

    @pytest.mark.asyncio
    async def test_execute_success(
        self,
        command: RelayEventCommand,
        mock_publisher: AsyncMock,
        sample_event_json: str,
    ) -> None:
        """Should return SUCCESS when publish succeeds."""
        result = await command.execute(sample_event_json)

        assert result.status == ResultStatus.SUCCESS
        mock_publisher.publish.assert_called_once_with(sample_event_json)

    @pytest.mark.asyncio
    async def test_execute_invalid_json(
        self,
        command: RelayEventCommand,
        mock_publisher: AsyncMock,
    ) -> None:
        """Should return DROP for invalid JSON."""
        result = await command.execute("not valid json {{{")

        assert result.status == ResultStatus.DROP
        assert "Invalid JSON" in (result.message or "")
        mock_publisher.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_connection_error(
        self,
        command: RelayEventCommand,
        mock_publisher: AsyncMock,
        sample_event_json: str,
    ) -> None:
        """Should return RETRYABLE on ConnectionError."""
        mock_publisher.publish.side_effect = ConnectionError("Connection refused")

        result = await command.execute(sample_event_json)

        assert result.status == ResultStatus.RETRYABLE
        assert "Connection refused" in (result.message or "")

    @pytest.mark.asyncio
    async def test_execute_timeout_error(
        self,
        command: RelayEventCommand,
        mock_publisher: AsyncMock,
        sample_event_json: str,
    ) -> None:
        """Should return RETRYABLE on TimeoutError."""
        mock_publisher.publish.side_effect = TimeoutError("Timeout")

        result = await command.execute(sample_event_json)

        assert result.status == ResultStatus.RETRYABLE

    @pytest.mark.asyncio
    async def test_execute_os_error(
        self,
        command: RelayEventCommand,
        mock_publisher: AsyncMock,
        sample_event_json: str,
    ) -> None:
        """Should return RETRYABLE on OSError."""
        mock_publisher.publish.side_effect = OSError("Network unreachable")

        result = await command.execute(sample_event_json)

        assert result.status == ResultStatus.RETRYABLE

    @pytest.mark.asyncio
    async def test_execute_unexpected_error(
        self,
        command: RelayEventCommand,
        mock_publisher: AsyncMock,
        sample_event_json: str,
    ) -> None:
        """Should return DROP on unexpected error."""
        mock_publisher.publish.side_effect = ValueError("Unexpected")

        result = await command.execute(sample_event_json)

        assert result.status == ResultStatus.DROP
        assert "Unexpected" in (result.message or "")
