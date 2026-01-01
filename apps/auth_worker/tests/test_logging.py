"""Logging 테스트."""

from __future__ import annotations

import logging
import os
from unittest.mock import patch

import pytest

from apps.auth_worker.setup.config import get_settings


class TestSetupLogging:
    """setup_logging 함수 테스트."""

    def setup_method(self) -> None:
        """테스트 전 설정."""
        # 캐시 클리어
        get_settings.cache_clear()

    def teardown_method(self) -> None:
        """테스트 후 정리."""
        # 로깅 상태 복원
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.setLevel(logging.WARNING)
        get_settings.cache_clear()

    def test_setup_logging_configures_root_logger(self) -> None:
        """루트 로거 설정 확인."""
        env_vars = {
            "AUTH_REDIS_URL": "redis://localhost:6379",
            "AUTH_AMQP_URL": "amqp://localhost:5672",
            "LOG_LEVEL": "DEBUG",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            from apps.auth_worker.setup.logging import setup_logging

            setup_logging()

            root_logger = logging.getLogger()
            assert root_logger.level == logging.DEBUG
            assert len(root_logger.handlers) == 1

    def test_setup_logging_adds_service_metadata(self) -> None:
        """서비스 메타데이터 추가 확인."""
        env_vars = {
            "AUTH_REDIS_URL": "redis://localhost:6379",
            "AUTH_AMQP_URL": "amqp://localhost:5672",
            "SERVICE_NAME": "test-worker",
            "SERVICE_VERSION": "1.2.3",
            "ENVIRONMENT": "test",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            from apps.auth_worker.setup.logging import setup_logging

            setup_logging()

            # LogRecord에 service 속성이 추가되는지 확인
            test_logger = logging.getLogger("test")
            record = test_logger.makeRecord(
                "test",
                logging.INFO,
                "test.py",
                1,
                "test message",
                (),
                None,
            )

            assert hasattr(record, "service")
            assert record.service["name"] == "test-worker"
            assert record.service["version"] == "1.2.3"
            assert record.service["environment"] == "test"

    def test_setup_logging_silences_external_libraries(self) -> None:
        """외부 라이브러리 로그 레벨 조정."""
        env_vars = {
            "AUTH_REDIS_URL": "redis://localhost:6379",
            "AUTH_AMQP_URL": "amqp://localhost:5672",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            from apps.auth_worker.setup.logging import setup_logging

            setup_logging()

            assert logging.getLogger("aio_pika").level == logging.WARNING
            assert logging.getLogger("aiormq").level == logging.WARNING
