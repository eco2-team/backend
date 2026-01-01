"""Tests for logging setup."""

from __future__ import annotations

import logging
import os
from unittest.mock import patch

import pytest


class TestSetupLogging:
    """setup_logging() tests."""

    @pytest.fixture(autouse=True)
    def clear_settings_cache(self) -> None:
        """Clear settings cache before each test."""
        from apps.auth_relay.setup.config import get_settings

        get_settings.cache_clear()

    @pytest.fixture(autouse=True)
    def reset_logging(self) -> None:
        """Reset logging config after each test."""
        yield
        # Reset root logger
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.WARNING)

    def test_configures_root_logger(self) -> None:
        """Should configure root logger with ECS formatter."""
        env = {
            "AUTH_REDIS_URL": "redis://localhost",
            "AUTH_AMQP_URL": "amqp://localhost",
            "LOG_LEVEL": "DEBUG",
        }

        with patch.dict(os.environ, env, clear=False):
            from apps.auth_relay.setup.logging import setup_logging

            setup_logging()

        root = logging.getLogger()
        assert root.level == logging.DEBUG
        assert len(root.handlers) == 1

    def test_silences_external_loggers(self) -> None:
        """Should silence noisy external loggers."""
        env = {
            "AUTH_REDIS_URL": "redis://localhost",
            "AUTH_AMQP_URL": "amqp://localhost",
        }

        with patch.dict(os.environ, env, clear=False):
            from apps.auth_relay.setup.logging import setup_logging

            setup_logging()

        assert logging.getLogger("aio_pika").level == logging.WARNING
        assert logging.getLogger("aiormq").level == logging.WARNING

    def test_injects_service_metadata(self) -> None:
        """Should inject service metadata into log records."""
        env = {
            "AUTH_REDIS_URL": "redis://localhost",
            "AUTH_AMQP_URL": "amqp://localhost",
            "SERVICE_NAME": "test-relay",
            "SERVICE_VERSION": "2.0.0",
            "ENVIRONMENT": "test",
        }

        with patch.dict(os.environ, env, clear=False):
            from apps.auth_relay.setup.logging import setup_logging

            setup_logging()

            # Create a log record to check metadata
            logger = logging.getLogger("test")
            record = logger.makeRecord("test", logging.INFO, "", 0, "test", (), None)

        assert hasattr(record, "service")
        assert record.service["name"] == "test-relay"
        assert record.service["version"] == "2.0.0"
        assert record.service["environment"] == "test"
