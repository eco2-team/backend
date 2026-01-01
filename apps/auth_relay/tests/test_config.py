"""Tests for config."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from apps.auth_relay.setup.config import Settings, get_settings


class TestSettings:
    """Settings tests."""

    def test_create_with_required_fields(self) -> None:
        """Should create with required fields."""
        settings = Settings(
            redis_url="redis://localhost:6379/0",
            amqp_url="amqp://localhost:5672/",
        )
        assert settings.redis_url == "redis://localhost:6379/0"
        assert settings.amqp_url == "amqp://localhost:5672/"

    def test_default_values(self) -> None:
        """Should have correct default values."""
        settings = Settings(
            redis_url="redis://localhost",
            amqp_url="amqp://localhost",
        )
        assert settings.poll_interval == 1.0
        assert settings.batch_size == 10
        assert settings.log_level == "INFO"
        assert settings.service_name == "auth-relay"
        assert settings.service_version == "1.0.0"
        assert settings.environment == "dev"

    def test_custom_values(self) -> None:
        """Should accept custom values."""
        settings = Settings(
            redis_url="redis://prod:6379",
            amqp_url="amqp://prod:5672",
            poll_interval=0.5,
            batch_size=20,
            log_level="DEBUG",
            environment="prod",
        )
        assert settings.poll_interval == 0.5
        assert settings.batch_size == 20
        assert settings.log_level == "DEBUG"
        assert settings.environment == "prod"

    def test_immutability(self) -> None:
        """Settings should be immutable (frozen dataclass)."""
        settings = Settings(
            redis_url="redis://localhost",
            amqp_url="amqp://localhost",
        )
        with pytest.raises(AttributeError):
            settings.redis_url = "new"  # type: ignore


class TestGetSettings:
    """get_settings() tests."""

    @pytest.fixture(autouse=True)
    def clear_cache(self) -> None:
        """Clear lru_cache before each test."""
        get_settings.cache_clear()

    def test_loads_from_environment(self) -> None:
        """Should load settings from environment."""
        env = {
            "AUTH_REDIS_URL": "redis://test:6379/0",
            "AUTH_AMQP_URL": "amqp://test:5672/",
            "RELAY_POLL_INTERVAL": "2.5",
            "RELAY_BATCH_SIZE": "50",
            "LOG_LEVEL": "DEBUG",
            "SERVICE_NAME": "test-relay",
            "SERVICE_VERSION": "2.0.0",
            "ENVIRONMENT": "test",
        }

        with patch.dict(os.environ, env, clear=False):
            settings = get_settings()

        assert settings.redis_url == "redis://test:6379/0"
        assert settings.amqp_url == "amqp://test:5672/"
        assert settings.poll_interval == 2.5
        assert settings.batch_size == 50
        assert settings.log_level == "DEBUG"
        assert settings.service_name == "test-relay"
        assert settings.environment == "test"

    def test_uses_defaults_for_optional(self) -> None:
        """Should use defaults for optional env vars."""
        env = {
            "AUTH_REDIS_URL": "redis://localhost",
            "AUTH_AMQP_URL": "amqp://localhost",
        }

        with patch.dict(os.environ, env, clear=True):
            settings = get_settings()

        assert settings.poll_interval == 1.0
        assert settings.batch_size == 10
        assert settings.log_level == "INFO"

    def test_raises_on_missing_required(self) -> None:
        """Should raise if required env var missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(KeyError):
                get_settings()
