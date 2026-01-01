"""ConsumerAdapter 테스트."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.auth_worker.application.common.result import CommandResult
from apps.auth_worker.presentation.adapters.consumer_adapter import ConsumerAdapter


class TestConsumerAdapter:
    """ConsumerAdapter 테스트."""

    @pytest.fixture
    def mock_handler(self) -> AsyncMock:
        """Mock BlacklistHandler."""
        handler = AsyncMock()
        handler.handle = AsyncMock(return_value=CommandResult.success())
        return handler

    @pytest.fixture
    def adapter(self, mock_handler: AsyncMock) -> ConsumerAdapter:
        """테스트용 Adapter 인스턴스."""
        return ConsumerAdapter(mock_handler)

    def _make_message(self, data: dict[str, Any]) -> MagicMock:
        """RabbitMQ 메시지 Mock 생성."""
        message = MagicMock()
        message.body = json.dumps(data).encode()
        message.ack = AsyncMock()
        message.nack = AsyncMock()
        return message

    @pytest.mark.asyncio
    async def test_on_message_success_acks(
        self,
        adapter: ConsumerAdapter,
        mock_handler: AsyncMock,
        sample_blacklist_data: dict[str, Any],
    ) -> None:
        """SUCCESS 결과시 ack."""
        message = self._make_message(sample_blacklist_data)

        await adapter.on_message(message)

        message.ack.assert_awaited_once()
        assert adapter.stats["processed"] == 1

    @pytest.mark.asyncio
    async def test_on_message_retryable_nacks_with_requeue(
        self,
        adapter: ConsumerAdapter,
        mock_handler: AsyncMock,
        sample_blacklist_data: dict[str, Any],
    ) -> None:
        """RETRYABLE 결과시 nack + requeue."""
        mock_handler.handle.return_value = CommandResult.retryable("Error")
        message = self._make_message(sample_blacklist_data)

        await adapter.on_message(message)

        message.nack.assert_awaited_once_with(requeue=True)
        assert adapter.stats["retried"] == 1

    @pytest.mark.asyncio
    async def test_on_message_drop_acks(
        self,
        adapter: ConsumerAdapter,
        mock_handler: AsyncMock,
        sample_blacklist_data: dict[str, Any],
    ) -> None:
        """DROP 결과시 ack (메시지 버림)."""
        mock_handler.handle.return_value = CommandResult.drop("Invalid")
        message = self._make_message(sample_blacklist_data)

        await adapter.on_message(message)

        message.ack.assert_awaited_once()
        assert adapter.stats["dropped"] == 1

    @pytest.mark.asyncio
    async def test_on_message_invalid_json_acks(
        self,
        adapter: ConsumerAdapter,
    ) -> None:
        """JSON 파싱 실패시 ack (버림)."""
        message = MagicMock()
        message.body = b"not valid json"
        message.ack = AsyncMock()
        message.nack = AsyncMock()

        await adapter.on_message(message)

        message.ack.assert_awaited_once()
        assert adapter.stats["dropped"] == 1

    @pytest.mark.asyncio
    async def test_on_message_unexpected_error_nacks(
        self,
        adapter: ConsumerAdapter,
        mock_handler: AsyncMock,
        sample_blacklist_data: dict[str, Any],
    ) -> None:
        """예상치 못한 에러시 nack + requeue."""
        mock_handler.handle.side_effect = RuntimeError("Unexpected")
        message = self._make_message(sample_blacklist_data)

        await adapter.on_message(message)

        message.nack.assert_awaited_once_with(requeue=True)
        assert adapter.stats["retried"] == 1

    @pytest.mark.asyncio
    async def test_stats_accumulates(
        self,
        adapter: ConsumerAdapter,
        mock_handler: AsyncMock,
        sample_blacklist_data: dict[str, Any],
    ) -> None:
        """통계가 누적됨."""
        # 3번 성공
        for _ in range(3):
            message = self._make_message(sample_blacklist_data)
            await adapter.on_message(message)

        # 2번 drop
        mock_handler.handle.return_value = CommandResult.drop("Invalid")
        for _ in range(2):
            message = self._make_message(sample_blacklist_data)
            await adapter.on_message(message)

        assert adapter.stats == {"processed": 3, "retried": 0, "dropped": 2}
