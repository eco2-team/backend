"""Pytest configuration for E2E tests.

E2E 테스트는 pytest-asyncio와 httpx가 필요합니다.

Requirements:
    pip install pytest-asyncio httpx

Run:
    pytest domains/character/tests/e2e/ -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# pytest-asyncio 필수
pytest_asyncio = pytest.importorskip("pytest_asyncio")

# Add project root to path for imports
project_root = Path(__file__).resolve().parents[4]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Environment setup for E2E tests
os.environ["AUTH_DISABLED"] = "true"
os.environ["CHARACTER_AUTH_DISABLED"] = "true"
os.environ["OTEL_ENABLED"] = "false"
os.environ["CHARACTER_CACHE_ENABLED"] = "false"


@pytest_asyncio.fixture
async def app():
    """Create FastAPI app for E2E testing."""
    from domains.character.main import create_app

    test_app = create_app()
    yield test_app


@pytest_asyncio.fixture
async def async_client(app):
    """Async HTTP client for E2E tests."""
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


@pytest_asyncio.fixture
async def mock_character_service():
    """Mock CharacterService for E2E tests."""
    from domains.character.schemas.catalog import CharacterProfile
    from domains.character.schemas.reward import CharacterRewardResponse

    service = AsyncMock()

    # Default catalog response
    service.catalog.return_value = [
        CharacterProfile(
            name="이코",
            type="기본",
            dialog="안녕!",
            match="플라스틱",
        )
    ]

    # Default reward response
    service.evaluate_reward.return_value = CharacterRewardResponse(
        received=True,
        already_owned=False,
        name="플라봇",
        dialog="플라스틱을 분리해줘서 고마워!",
        match_reason="플라스틱>페트병",
        character_type="플라스틱",
        type="플라스틱",
    )

    return service
