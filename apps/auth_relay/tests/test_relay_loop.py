"""Tests for RelayLoop."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from apps.auth_relay.application.common.result import RelayResult
from apps.auth_relay.presentation.relay_loop import RelayLoop


class TestRelayLoop:
    """RelayLoop tests."""

    @pytest.fixture
    def relay_loop(
        self,
        mock_outbox_reader: AsyncMock,
        mock_relay_command: AsyncMock,
    ) -> RelayLoop:
        """Create relay loop with mocks."""
        return RelayLoop(
            mock_outbox_reader,
            mock_relay_command,
            poll_interval=0.01,
            batch_size=5,
        )

    @pytest.mark.asyncio
    async def test_process_batch_success(
        self,
        relay_loop: RelayLoop,
        mock_outbox_reader: AsyncMock,
        mock_relay_command: AsyncMock,
    ) -> None:
        """Should process events and return count."""
        # Setup: 2 events then None
        mock_outbox_reader.pop.side_effect = ['{"jti":"1"}', '{"jti":"2"}', None]
        mock_relay_command.execute.return_value = RelayResult.success()

        processed = await relay_loop._process_batch()

        assert processed == 2
        assert mock_relay_command.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_process_batch_empty_queue(
        self,
        relay_loop: RelayLoop,
        mock_outbox_reader: AsyncMock,
    ) -> None:
        """Should return 0 when queue is empty."""
        mock_outbox_reader.pop.return_value = None

        processed = await relay_loop._process_batch()

        assert processed == 0

    @pytest.mark.asyncio
    async def test_process_batch_retryable(
        self,
        relay_loop: RelayLoop,
        mock_outbox_reader: AsyncMock,
        mock_relay_command: AsyncMock,
    ) -> None:
        """Should push back and stop batch on RETRYABLE."""
        mock_outbox_reader.pop.side_effect = ['{"jti":"1"}', '{"jti":"2"}']
        mock_relay_command.execute.return_value = RelayResult.retryable("Connection error")

        processed = await relay_loop._process_batch()

        assert processed == 0
        mock_outbox_reader.push_back.assert_called_once_with('{"jti":"1"}')
        # Should stop after first retryable
        assert mock_relay_command.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_process_batch_drop(
        self,
        relay_loop: RelayLoop,
        mock_outbox_reader: AsyncMock,
        mock_relay_command: AsyncMock,
    ) -> None:
        """Should push to DLQ on DROP."""
        mock_outbox_reader.pop.side_effect = ['{"jti":"1"}', None]
        mock_relay_command.execute.return_value = RelayResult.drop("Invalid format")

        processed = await relay_loop._process_batch()

        assert processed == 0
        mock_outbox_reader.push_to_dlq.assert_called_once_with('{"jti":"1"}')

    @pytest.mark.asyncio
    async def test_process_batch_mixed_results(
        self,
        relay_loop: RelayLoop,
        mock_outbox_reader: AsyncMock,
        mock_relay_command: AsyncMock,
    ) -> None:
        """Should handle mixed success/drop results."""
        mock_outbox_reader.pop.side_effect = ['{"jti":"1"}', '{"jti":"2"}', None]
        mock_relay_command.execute.side_effect = [
            RelayResult.success(),
            RelayResult.drop("Bad"),
        ]

        processed = await relay_loop._process_batch()

        assert processed == 1
        mock_outbox_reader.push_to_dlq.assert_called_once()

    def test_stop(self, relay_loop: RelayLoop) -> None:
        """stop() should set shutdown flag."""
        relay_loop.stop()
        assert relay_loop._shutdown is True

    def test_stats(self, relay_loop: RelayLoop) -> None:
        """stats should return processed/failed counts."""
        relay_loop._processed_total = 10
        relay_loop._failed_total = 2

        stats = relay_loop.stats

        assert stats["processed"] == 10
        assert stats["failed"] == 2

    def test_initial_stats(self, relay_loop: RelayLoop) -> None:
        """Initial stats should be zero."""
        stats = relay_loop.stats
        assert stats["processed"] == 0
        assert stats["failed"] == 0

    @pytest.mark.asyncio
    async def test_batch_size_limit(
        self,
        mock_outbox_reader: AsyncMock,
        mock_relay_command: AsyncMock,
    ) -> None:
        """Should respect batch_size limit."""
        loop = RelayLoop(
            mock_outbox_reader,
            mock_relay_command,
            batch_size=2,
        )
        # More events than batch size
        mock_outbox_reader.pop.side_effect = ['{"1"}', '{"2"}', '{"3"}', None]
        mock_relay_command.execute.return_value = RelayResult.success()

        processed = await loop._process_batch()

        assert processed == 2
        assert mock_relay_command.execute.call_count == 2
