"""Config 테스트."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from apps.auth_worker.setup.config import Settings, get_settings


class TestSettings:
    """Settings 테스트."""

    def test_settings_creation(self) -> None:
        """Settings 인스턴스 생성."""
        settings = Settings(
            redis_url="redis://localhost:6379",
            amqp_url="amqp://localhost:5672",
        )

        assert settings.redis_url == "redis://localhost:6379"
        assert settings.amqp_url == "amqp://localhost:5672"
        assert settings.log_level == "INFO"  # 기본값
        assert settings.service_name == "auth-worker"  # 기본값

    def test_settings_with_custom_values(self) -> None:
        """커스텀 값으로 Settings 생성."""
        settings = Settings(
            redis_url="redis://prod:6379",
            amqp_url="amqp://prod:5672",
            log_level="DEBUG",
            service_name="custom-worker",
            service_version="2.0.0",
            environment="prod",
        )

        assert settings.log_level == "DEBUG"
        assert settings.service_name == "custom-worker"
        assert settings.service_version == "2.0.0"
        assert settings.environment == "prod"

    def test_settings_immutable(self) -> None:
        """frozen=True 확인."""
        settings = Settings(
            redis_url="redis://localhost:6379",
            amqp_url="amqp://localhost:5672",
        )

        with pytest.raises(AttributeError):
            settings.redis_url = "new_url"  # type: ignore


class TestGetSettings:
    """get_settings 함수 테스트."""

    def test_get_settings_from_env(self) -> None:
        """환경 변수에서 설정 로드."""
        # lru_cache 초기화
        get_settings.cache_clear()

        env_vars = {
            "AUTH_REDIS_URL": "redis://test:6379",
            "AUTH_AMQP_URL": "amqp://test:5672",
            "LOG_LEVEL": "DEBUG",
            "SERVICE_NAME": "test-worker",
            "SERVICE_VERSION": "3.0.0",
            "ENVIRONMENT": "test",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            settings = get_settings()

            assert settings.redis_url == "redis://test:6379"
            assert settings.amqp_url == "amqp://test:5672"
            assert settings.log_level == "DEBUG"
            assert settings.service_name == "test-worker"
            assert settings.service_version == "3.0.0"
            assert settings.environment == "test"

        # 테스트 후 캐시 정리
        get_settings.cache_clear()

    def test_get_settings_missing_required_env(self) -> None:
        """필수 환경 변수 누락시 KeyError."""
        get_settings.cache_clear()

        # AUTH_REDIS_URL, AUTH_AMQP_URL 없이 호출
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(KeyError):
                get_settings()

        get_settings.cache_clear()

    def test_get_settings_defaults(self) -> None:
        """선택적 환경 변수 기본값."""
        get_settings.cache_clear()

        env_vars = {
            "AUTH_REDIS_URL": "redis://localhost:6379",
            "AUTH_AMQP_URL": "amqp://localhost:5672",
        }

        # 선택적 환경 변수 제거
        with patch.dict(os.environ, env_vars, clear=True):
            settings = get_settings()

            assert settings.log_level == "INFO"
            assert settings.service_name == "auth-worker"
            assert settings.service_version == "1.0.0"
            assert settings.environment == "dev"

        get_settings.cache_clear()

    def test_get_settings_cached(self) -> None:
        """설정 캐싱 확인."""
        get_settings.cache_clear()

        env_vars = {
            "AUTH_REDIS_URL": "redis://cache-test:6379",
            "AUTH_AMQP_URL": "amqp://cache-test:5672",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings1 = get_settings()
            settings2 = get_settings()

            assert settings1 is settings2  # 동일 객체

        get_settings.cache_clear()
