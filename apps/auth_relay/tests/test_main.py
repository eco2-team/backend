"""Tests for main entry point."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAuthRelay:
    """AuthRelay tests."""

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
            "SERVICE_NAME": "auth-relay",
            "SERVICE_VERSION": "1.0.0",
            "ENVIRONMENT": "test",
        }

    @pytest.mark.asyncio
    async def test_start_initializes_container(self, env_vars: dict[str, str]) -> None:
        """start() should initialize container and run loop."""
        mock_container = MagicMock()
        mock_container.init = AsyncMock()
        mock_container.close = AsyncMock()
        mock_relay_loop = AsyncMock()
        mock_relay_loop.run = AsyncMock(side_effect=asyncio.CancelledError)
        mock_relay_loop.stop = MagicMock()
        mock_relay_loop.stats = {"processed": 0, "failed": 0}
        mock_container.relay_loop = mock_relay_loop

        with patch.dict(os.environ, env_vars, clear=False):
            with patch("auth_relay.main.Container", return_value=mock_container):
                with patch("auth_relay.main.setup_logging"):
                    from auth_relay.main import AuthRelay

                    relay = AuthRelay()
                    relay._container = mock_container

                    with pytest.raises(asyncio.CancelledError):
                        await relay.start()

        mock_container.init.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_closes_container(self, env_vars: dict[str, str]) -> None:
        """_cleanup() should close container."""
        mock_container = MagicMock()
        mock_container.close = AsyncMock()
        mock_relay_loop = MagicMock()
        mock_relay_loop.stats = {"processed": 5, "failed": 1}
        mock_container.relay_loop = mock_relay_loop

        with patch.dict(os.environ, env_vars, clear=False):
            from auth_relay.main import AuthRelay

            relay = AuthRelay()
            relay._container = mock_container

            await relay._cleanup()

        mock_container.close.assert_called_once()

    def test_handle_shutdown_stops_loop(self, env_vars: dict[str, str]) -> None:
        """_handle_shutdown() should stop relay loop."""
        mock_container = MagicMock()
        mock_relay_loop = MagicMock()
        mock_relay_loop.stop = MagicMock()
        mock_container.relay_loop = mock_relay_loop

        with patch.dict(os.environ, env_vars, clear=False):
            from auth_relay.main import AuthRelay

            relay = AuthRelay()
            relay._container = mock_container

            relay._handle_shutdown()

        mock_relay_loop.stop.assert_called_once()


class TestMain:
    """main() function tests."""

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
    async def test_main_calls_start(self, env_vars: dict[str, str]) -> None:
        """main() should call relay.start()."""
        mock_relay = MagicMock()
        mock_relay.start = AsyncMock()

        with patch.dict(os.environ, env_vars, clear=False):
            with patch("auth_relay.main.setup_logging"):
                with patch("auth_relay.main.AuthRelay", return_value=mock_relay):
                    from auth_relay.main import main

                    await main()

        mock_relay.start.assert_called_once()
