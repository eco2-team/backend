"""Dependencies 테스트."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.auth_worker.setup.config import get_settings


class TestContainer:
    """Container 테스트."""

    def setup_method(self) -> None:
        """테스트 전 설정."""
        get_settings.cache_clear()

    def teardown_method(self) -> None:
        """테스트 후 정리."""
        get_settings.cache_clear()

    def test_container_init_without_settings(self) -> None:
        """환경 변수 없이 Container 생성시 KeyError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(KeyError):
                from apps.auth_worker.setup.dependencies import Container

                Container()

    def test_container_properties_before_init(self) -> None:
        """init() 전에 속성 접근시 RuntimeError."""
        env_vars = {
            "AUTH_REDIS_URL": "redis://localhost:6379",
            "AUTH_AMQP_URL": "amqp://localhost:5672",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            from apps.auth_worker.setup.dependencies import Container

            container = Container()

            with pytest.raises(RuntimeError, match="Container not initialized"):
                _ = container.rabbitmq_client

            with pytest.raises(RuntimeError, match="Container not initialized"):
                _ = container.consumer_adapter

            with pytest.raises(RuntimeError, match="Container not initialized"):
                _ = container.persist_command

    @pytest.mark.asyncio
    async def test_container_init_and_close(self) -> None:
        """Container 초기화 및 종료."""
        env_vars = {
            "AUTH_REDIS_URL": "redis://localhost:6379",
            "AUTH_AMQP_URL": "amqp://localhost:5672",
        }

        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock()
        mock_redis.close = AsyncMock()

        with patch.dict(os.environ, env_vars, clear=True):
            with patch(
                "apps.auth_worker.setup.dependencies.aioredis.from_url",
                return_value=mock_redis,
            ):
                from apps.auth_worker.setup.dependencies import Container

                container = Container()
                await container.init()

                # 속성 접근 가능
                assert container.rabbitmq_client is not None
                assert container.consumer_adapter is not None
                assert container.persist_command is not None

                # 종료
                await container.close()
                mock_redis.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_container_close_without_init(self) -> None:
        """init() 없이 close() 호출."""
        env_vars = {
            "AUTH_REDIS_URL": "redis://localhost:6379",
            "AUTH_AMQP_URL": "amqp://localhost:5672",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            from apps.auth_worker.setup.dependencies import Container

            container = Container()

            # 에러 없이 종료
            await container.close()
