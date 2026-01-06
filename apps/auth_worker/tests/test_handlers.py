"""BlacklistHandler 테스트."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from apps.auth_worker.application.common.result import CommandResult, ResultStatus
from apps.auth_worker.presentation.handlers.blacklist_handler import BlacklistHandler


class TestBlacklistHandler:
    """BlacklistHandler 테스트."""

    @pytest.fixture
    def mock_command(self) -> AsyncMock:
        """Mock PersistBlacklistCommand."""
        command = AsyncMock()
        command.execute = AsyncMock(return_value=CommandResult.success())
        return command

    @pytest.fixture
    def handler(self, mock_command: AsyncMock) -> BlacklistHandler:
        """테스트용 Handler 인스턴스."""
        return BlacklistHandler(mock_command)

    @pytest.mark.asyncio
    async def test_handle_success(
        self,
        handler: BlacklistHandler,
        mock_command: AsyncMock,
        sample_blacklist_data: dict[str, Any],
    ) -> None:
        """정상 처리 성공."""
        result = await handler.handle(sample_blacklist_data)

        assert result.status == ResultStatus.SUCCESS
        mock_command.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_command_retryable(
        self,
        handler: BlacklistHandler,
        mock_command: AsyncMock,
        sample_blacklist_data: dict[str, Any],
    ) -> None:
        """Command가 RETRYABLE 반환."""
        mock_command.execute.return_value = CommandResult.retryable("Error")

        result = await handler.handle(sample_blacklist_data)

        assert result.status == ResultStatus.RETRYABLE

    @pytest.mark.asyncio
    async def test_handle_command_drop(
        self,
        handler: BlacklistHandler,
        mock_command: AsyncMock,
        sample_blacklist_data: dict[str, Any],
    ) -> None:
        """Command가 DROP 반환."""
        mock_command.execute.return_value = CommandResult.drop("Invalid")

        result = await handler.handle(sample_blacklist_data)

        assert result.status == ResultStatus.DROP

    @pytest.mark.asyncio
    async def test_handle_invalid_format_drops(
        self,
        handler: BlacklistHandler,
    ) -> None:
        """잘못된 메시지 형식은 DROP."""
        invalid_data = {"invalid": "data"}  # 필수 필드 누락

        result = await handler.handle(invalid_data)

        assert result.status == ResultStatus.DROP
        assert "Invalid message format" in (result.message or "")

    @pytest.mark.asyncio
    async def test_handle_missing_jti_drops(
        self,
        handler: BlacklistHandler,
    ) -> None:
        """jti 필드 누락시 DROP."""
        data = {
            "type": "add",
            "expires_at": "2025-12-31T23:59:59",
            "timestamp": "2025-01-01T00:00:00",
        }

        result = await handler.handle(data)

        assert result.status == ResultStatus.DROP

    @pytest.mark.asyncio
    async def test_handle_unexpected_error_retryable(
        self,
        handler: BlacklistHandler,
        mock_command: AsyncMock,
        sample_blacklist_data: dict[str, Any],
    ) -> None:
        """예상치 못한 에러는 RETRYABLE."""
        mock_command.execute.side_effect = RuntimeError("Unexpected")

        result = await handler.handle(sample_blacklist_data)

        assert result.status == ResultStatus.RETRYABLE
