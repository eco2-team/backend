"""Pytest configuration for Chat integration tests.

실제 OpenAI API를 호출하는 통합 테스트용 fixtures.

Requirements:
    - OPENAI_API_KEY 환경변수 설정 필요
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# pytest-asyncio 필수
pytest_asyncio = pytest.importorskip("pytest_asyncio")

# Add project root to path for imports
project_root = Path(__file__).resolve().parents[4]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Environment setup for integration tests
os.environ["OTEL_ENABLED"] = "false"
os.environ["AUTH_DISABLED"] = "true"
os.environ["CHAT_AUTH_DISABLED"] = "true"


def pytest_configure(config):
    """Add custom markers."""
    config.addinivalue_line(
        "markers",
        "requires_openai: marks test as requiring OPENAI_API_KEY (skip if not set)",
    )


def pytest_collection_modifyitems(config, items):
    """Skip tests that require OPENAI_API_KEY if not set."""
    if os.environ.get("OPENAI_API_KEY"):
        return

    skip_openai = pytest.mark.skip(reason="OPENAI_API_KEY not set")
    for item in items:
        if "requires_openai" in item.keywords:
            item.add_marker(skip_openai)


@pytest.fixture
def openai_api_key() -> str | None:
    """Get OPENAI_API_KEY from environment."""
    return os.environ.get("OPENAI_API_KEY")


@pytest_asyncio.fixture
async def app():
    """Create FastAPI app for integration testing."""
    from domains.chat.main import create_app

    test_app = create_app()
    yield test_app


@pytest_asyncio.fixture
async def async_client(app):
    """Async HTTP client for integration tests."""
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=60.0,  # OpenAI API 호출 대기
    ) as client:
        yield client


@pytest.fixture
def test_user_headers() -> dict[str, str]:
    """Test user headers for authenticated requests."""
    return {
        "x-user-id": "12345678-1234-5678-1234-567812345678",
        "x-auth-provider": "test",
    }


@pytest.fixture
def sample_text_questions() -> list[str]:
    """Sample text questions for testing."""
    return [
        "페트병 버리는 방법 알려줘",
        "플라스틱 분리수거 어떻게 해?",
        "유리병은 어디에 버려?",
        "종이 컵 재활용 되나요?",
        "음식물 쓰레기 처리 방법",
    ]


@pytest.fixture
def sample_image_urls() -> list[str]:
    """Sample image URLs for Vision API testing."""
    return [
        # 테스트용 공개 이미지 URL (실제 폐기물 이미지로 교체 가능)
        "https://images.unsplash.com/photo-1604187351574-c75ca79f5807?w=400",  # plastic bottle
    ]
