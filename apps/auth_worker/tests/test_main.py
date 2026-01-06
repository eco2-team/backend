"""Main 테스트."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.auth_worker.setup.config import get_settings


class TestAuthWorker:
    """AuthWorker 테스트."""

    def setup_method(self) -> None:
        """테스트 전 설정."""
        get_settings.cache_clear()

    def teardown_method(self) -> None:
        """테스트 후 정리."""
        get_settings.cache_clear()

    def test_auth_worker_init(self) -> None:
        """AuthWorker 초기화."""
        env_vars = {
            "AUTH_REDIS_URL": "redis://localhost:6379",
            "AUTH_AMQP_URL": "amqp://localhost:5672",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with patch(
                "apps.auth_worker.main.Container",
                return_value=MagicMock(),
            ):
                from apps.auth_worker.main import AuthWorker

                worker = AuthWorker()
                assert worker._shutdown is False

    def test_handle_shutdown(self) -> None:
        """Shutdown 핸들러 테스트."""
        env_vars = {
            "AUTH_REDIS_URL": "redis://localhost:6379",
            "AUTH_AMQP_URL": "amqp://localhost:5672",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with patch(
                "apps.auth_worker.main.Container",
                return_value=MagicMock(),
            ):
                from apps.auth_worker.main import AuthWorker

                worker = AuthWorker()
                assert worker._shutdown is False

                worker._handle_shutdown()
                assert worker._shutdown is True

    @pytest.mark.asyncio
    async def test_cleanup(self) -> None:
        """Cleanup 테스트."""
        env_vars = {
            "AUTH_REDIS_URL": "redis://localhost:6379",
            "AUTH_AMQP_URL": "amqp://localhost:5672",
        }

        mock_container = MagicMock()
        mock_container.consumer_adapter.stats = {
            "processed": 10,
            "retried": 2,
            "dropped": 1,
        }
        mock_container.close = AsyncMock()

        with patch.dict(os.environ, env_vars, clear=True):
            with patch(
                "apps.auth_worker.main.Container",
                return_value=mock_container,
            ):
                from apps.auth_worker.main import AuthWorker

                worker = AuthWorker()
                await worker._cleanup()

                mock_container.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_initializes_and_connects(self) -> None:
        """Start 메서드 테스트."""
        env_vars = {
            "AUTH_REDIS_URL": "redis://localhost:6379",
            "AUTH_AMQP_URL": "amqp://localhost:5672",
        }

        mock_container = MagicMock()
        mock_container.init = AsyncMock()
        mock_container.rabbitmq_client.connect = AsyncMock()
        mock_container.rabbitmq_client.start_consuming = AsyncMock(
            side_effect=Exception("Test stop")
        )
        mock_container.consumer_adapter.stats = {
            "processed": 0,
            "retried": 0,
            "dropped": 0,
        }
        mock_container.close = AsyncMock()

        with patch.dict(os.environ, env_vars, clear=True):
            with patch(
                "apps.auth_worker.main.Container",
                return_value=mock_container,
            ):
                with patch("asyncio.get_event_loop") as mock_loop:
                    mock_loop.return_value.add_signal_handler = MagicMock()

                    from apps.auth_worker.main import AuthWorker

                    worker = AuthWorker()

                    # start_consuming이 예외를 던지므로 finally에서 cleanup 실행
                    with pytest.raises(Exception, match="Test stop"):
                        await worker.start()

                    mock_container.init.assert_awaited_once()
                    mock_container.rabbitmq_client.connect.assert_awaited_once()
                    mock_container.close.assert_awaited_once()


class TestMain:
    """main 함수 테스트."""

    def setup_method(self) -> None:
        """테스트 전 설정."""
        get_settings.cache_clear()

    def teardown_method(self) -> None:
        """테스트 후 정리."""
        get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_main_function(self) -> None:
        """main() 함수 테스트."""
        env_vars = {
            "AUTH_REDIS_URL": "redis://localhost:6379",
            "AUTH_AMQP_URL": "amqp://localhost:5672",
        }

        mock_worker = MagicMock()
        mock_worker.start = AsyncMock()

        with patch.dict(os.environ, env_vars, clear=True):
            with patch("apps.auth_worker.main.setup_logging") as mock_setup_logging:
                with patch(
                    "apps.auth_worker.main.AuthWorker",
                    return_value=mock_worker,
                ):
                    from apps.auth_worker.main import main

                    await main()

                    mock_setup_logging.assert_called_once()
                    mock_worker.start.assert_awaited_once()
