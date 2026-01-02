"""Test Configuration and Fixtures.

pytest 설정 및 공통 픽스처.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Generator
from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest

if TYPE_CHECKING:
    pass


# ============================================================
# Environment
# ============================================================


@pytest.fixture(scope="session", autouse=True)
def _test_env() -> Generator[None, None, None]:
    """Set test environment variables."""
    original = os.environ.copy()
    os.environ.update(
        {
            "AUTH_DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
            "AUTH_REDIS_URL": "redis://localhost:6379/1",
            "JWT_SECRET_KEY": "test-secret-key-for-testing-only",
            "ENVIRONMENT": "test",
        }
    )
    yield
    os.environ.clear()
    os.environ.update(original)


# ============================================================
# Domain Fixtures
# ============================================================


@pytest.fixture
def user_id() -> uuid.UUID:
    """테스트용 User ID."""
    return uuid.uuid4()


@pytest.fixture
def email() -> str:
    """테스트용 이메일."""
    return "test@example.com"


@pytest.fixture
def now() -> datetime:
    """현재 시간 (UTC)."""
    return datetime.now(timezone.utc)


# ============================================================
# Mock Gateway Fixtures
# ============================================================


@pytest.fixture
def mock_users_command_gateway() -> MagicMock:
    """Mock UsersCommandGateway."""
    from apps.auth.application.users.ports import UsersCommandGateway

    return create_autospec(UsersCommandGateway, instance=True)


@pytest.fixture
def mock_users_query_gateway() -> MagicMock:
    """Mock UsersQueryGateway."""
    from apps.auth.application.users.ports import UsersQueryGateway

    return create_autospec(UsersQueryGateway, instance=True)


# Deprecated aliases for backward compatibility
mock_user_command_gateway = mock_users_command_gateway
mock_user_query_gateway = mock_users_query_gateway


@pytest.fixture
def mock_token_service() -> MagicMock:
    """Mock TokenService."""
    from apps.auth.application.token.ports import TokenIssuer

    return create_autospec(TokenIssuer, instance=True)


@pytest.fixture
def mock_state_store() -> AsyncMock:
    """Mock StateStore."""
    mock = AsyncMock()
    mock.save_state = AsyncMock(return_value=True)
    mock.get_and_delete_state = AsyncMock()
    return mock


@pytest.fixture
def mock_token_blacklist() -> AsyncMock:
    """Mock TokenBlacklist."""
    mock = AsyncMock()
    mock.add = AsyncMock(return_value=True)
    mock.is_blacklisted = AsyncMock(return_value=False)
    return mock


@pytest.fixture
def mock_flusher() -> AsyncMock:
    """Mock Flusher."""
    mock = AsyncMock()
    mock.flush = AsyncMock()
    return mock


@pytest.fixture
def mock_transaction_manager() -> AsyncMock:
    """Mock TransactionManager."""
    mock = AsyncMock()
    mock.begin = AsyncMock()
    mock.commit = AsyncMock()
    mock.rollback = AsyncMock()
    return mock
