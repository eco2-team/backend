"""Tests for Container (DI)."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest


class TestContainer:
    """Container tests."""

    @pytest.fixture(autouse=True)
    def clear_settings_cache(self) -> None:
        """Clear settings cache before each test."""
        from auth_relay.setup.config import get_settings

        get_settings.cache_clear()

    @pytest.fixture
    def env_vars(self) -> dict[str, str]:
        """Environment variables for testing."""
        return {
            "AUTH_REDIS_URL": "redis://localhost:6379/0",
            "AUTH_AMQP_URL": "amqp://localhost:5672/",
        }

    @pytest.mark.asyncio
    async def test_init_creates_dependencies(self, env_vars: dict[str, str]) -> None:
        """init() should create all dependencies."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()

        mock_publisher = AsyncMock()
        mock_publisher.connect = AsyncMock()

        with patch.dict(os.environ, env_vars, clear=False):
            with patch("redis.asyncio.from_url", return_value=mock_redis):
                with patch(
                    "auth_relay.setup.dependencies.RabbitMQEventPublisher",
                    return_value=mock_publisher,
                ):
                    from auth_relay.setup.dependencies import Container

                    container = Container()
                    await container.init()

        mock_redis.ping.assert_called_once()
        mock_publisher.connect.assert_called_once()
        assert container._relay_loop is not None

    @pytest.mark.asyncio
    async def test_close_cleans_up_resources(self, env_vars: dict[str, str]) -> None:
        """close() should clean up all resources."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_redis.close = AsyncMock()

        mock_publisher = AsyncMock()
        mock_publisher.connect = AsyncMock()
        mock_publisher.close = AsyncMock()

        with patch.dict(os.environ, env_vars, clear=False):
            with patch("redis.asyncio.from_url", return_value=mock_redis):
                with patch(
                    "auth_relay.setup.dependencies.RabbitMQEventPublisher",
                    return_value=mock_publisher,
                ):
                    from auth_relay.setup.dependencies import Container

                    container = Container()
                    await container.init()
                    await container.close()

        mock_publisher.close.assert_called_once()
        mock_redis.close.assert_called_once()

    def test_relay_loop_raises_if_not_initialized(self, env_vars: dict[str, str]) -> None:
        """relay_loop property should raise if not initialized."""
        with patch.dict(os.environ, env_vars, clear=False):
            from auth_relay.setup.dependencies import Container

            container = Container()

        with pytest.raises(RuntimeError, match="Container not initialized"):
            _ = container.relay_loop

    @pytest.mark.asyncio
    async def test_relay_loop_returns_initialized_loop(self, env_vars: dict[str, str]) -> None:
        """relay_loop property should return loop after init."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()

        mock_publisher = AsyncMock()
        mock_publisher.connect = AsyncMock()

        with patch.dict(os.environ, env_vars, clear=False):
            with patch("redis.asyncio.from_url", return_value=mock_redis):
                with patch(
                    "auth_relay.setup.dependencies.RabbitMQEventPublisher",
                    return_value=mock_publisher,
                ):
                    from auth_relay.setup.dependencies import Container

                    container = Container()
                    await container.init()
                    loop = container.relay_loop

        from auth_relay.presentation.relay_loop import RelayLoop

        assert isinstance(loop, RelayLoop)
