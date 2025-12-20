"""Pytest configuration for Character domain tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

try:
    import pytest_asyncio
except ImportError:
    pytest_asyncio = None  # pytest-asyncio not installed

# E2E 테스트 디렉토리 기본 제외 (pytest-asyncio 필요)
# 로컬에서 E2E 테스트 실행: pytest domains/character/tests/e2e/ -v
collect_ignore = ["e2e"]

# Add project root to path for imports
project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Add extra path for shared modules
extra_path = project_root / "domains"
if str(extra_path) not in sys.path:
    sys.path.insert(0, str(extra_path))

# Disable tracing and cache for tests
os.environ["OTEL_ENABLED"] = "false"
os.environ["AUTH_DISABLED"] = "true"
os.environ["CHARACTER_CACHE_ENABLED"] = "false"


# ============================================================================
# Global State Reset Fixtures (테스트 격리)
# ============================================================================


@pytest.fixture(autouse=True)
def reset_global_state():
    """모든 테스트 전후로 글로벌 상태를 리셋합니다.

    이 fixture는 autouse=True로 설정되어 모든 테스트에 자동 적용됩니다.
    테스트 간 상태 오염을 방지합니다.
    """
    # Setup: 테스트 전 상태 리셋
    from domains.character.core.cache import reset_cache_client
    from domains.character.services.evaluators import reset_registry

    reset_cache_client()
    reset_registry()

    yield

    # Teardown: 테스트 후 상태 정리
    reset_cache_client()


# ============================================================================
# Test Fixtures for Unit Tests
# ============================================================================


@pytest.fixture
def mock_character():
    """Factory fixture for creating mock characters."""

    def _create(
        name: str = "테스트캐릭터",
        type_label: str = "테스트",
        match_label: str = "플라스틱",
        dialog: str = "안녕!",
    ):
        char = MagicMock()
        char.id = uuid4()
        char.name = name
        char.type_label = type_label
        char.match_label = match_label
        char.dialog = dialog
        char.description = None
        char.code = f"{name.upper()[:4]}001"
        return char

    return _create


@pytest.fixture
def test_user_id() -> UUID:
    """Test user ID fixture."""
    return UUID("12345678-1234-5678-1234-567812345678")


# Note: E2E fixtures are in tests/e2e/conftest.py
