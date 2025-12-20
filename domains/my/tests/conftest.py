"""Pytest fixtures for My domain tests."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# 프로젝트 루트를 PYTHONPATH에 추가
ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture
def mock_session():
    """Mock AsyncSession for service tests."""
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock()
    session.get = AsyncMock()
    return session


@pytest.fixture
def mock_user_repo():
    """Mock UserRepository."""
    repo = MagicMock()
    repo.get_by_auth_user_id = AsyncMock()
    repo.create_from_auth = AsyncMock()
    repo.update_user = AsyncMock()
    repo.update_auth_user_phone = AsyncMock()
    repo.delete_user = AsyncMock()
    repo.metrics = AsyncMock(return_value={"total_users": 100})
    return repo


@pytest.fixture
def mock_social_repo():
    """Mock UserSocialAccountRepository."""
    repo = MagicMock()
    repo.list_by_user_id = AsyncMock(return_value=[])
    repo.count_by_provider = AsyncMock(return_value={"kakao": 50, "google": 50})
    return repo


@pytest.fixture
def mock_character_repo():
    """Mock UserCharacterRepository."""
    repo = MagicMock()
    repo.list_by_user = AsyncMock(return_value=[])
    repo.get_by_user_and_character = AsyncMock(return_value=None)
    repo.owns_character_by_name = AsyncMock(return_value=False)
    repo.grant_character = AsyncMock()
    return repo


@pytest.fixture
def mock_character_client():
    """Mock CharacterClient for gRPC calls."""
    client = MagicMock()
    client.get_default_character = AsyncMock(return_value=None)
    client.close = AsyncMock()
    return client
