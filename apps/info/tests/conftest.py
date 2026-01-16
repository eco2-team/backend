"""Test Configuration and Fixtures.

pytest 설정 및 공통 픽스처.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest

from info.domain.entities import NewsArticle

# pytest-asyncio 자동 모드 설정
pytest_plugins = ("pytest_asyncio",)


# ============================================================
# Environment
# ============================================================


@pytest.fixture(scope="session", autouse=True)
def _test_env() -> Generator[None, None, None]:
    """Set test environment variables."""
    original = os.environ.copy()
    os.environ.update(
        {
            "INFO_REDIS_URL": "redis://localhost:6379/1",
            "INFO_NAVER_CLIENT_ID": "test-client-id",
            "INFO_NAVER_CLIENT_SECRET": "test-client-secret",
            "INFO_NEWSDATA_API_KEY": "test-api-key",
            "INFO_NEWS_CACHE_TTL": "3600",
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
def now() -> datetime:
    """현재 시간 (UTC)."""
    return datetime.now(timezone.utc)


@pytest.fixture
def sample_article(now: datetime) -> NewsArticle:
    """샘플 뉴스 기사."""
    return NewsArticle(
        id="naver_abc123",
        title="환경부 분리배출 정책 변경",
        url="https://example.com/news/1",
        snippet="환경부가 새로운 분리배출 가이드라인을 발표했습니다.",
        source="naver",
        source_name="환경일보",
        published_at=now,
        thumbnail_url="https://example.com/image.jpg",
        category="environment",
    )


@pytest.fixture
def sample_articles(now: datetime) -> list[NewsArticle]:
    """샘플 뉴스 기사 목록."""
    from datetime import timedelta

    return [
        NewsArticle(
            id="naver_001",
            title="환경 정책 뉴스",
            url="https://example.com/news/1",
            snippet="환경 관련 기사입니다.",
            source="naver",
            source_name="환경일보",
            published_at=now,
            category=None,
        ),
        NewsArticle(
            id="newsdata_002",
            title="AI 기술 발전",
            url="https://example.com/news/2",
            snippet="인공지능 AI 머신러닝 기술이 발전했습니다.",
            source="newsdata",
            source_name="TechNews",
            published_at=now - timedelta(hours=1),
            thumbnail_url="https://example.com/ai.jpg",
            category=None,
        ),
        NewsArticle(
            id="naver_003",
            title="신재생에너지 투자 확대",
            url="https://example.com/news/3",
            snippet="태양광 에너지 투자가 늘어났습니다.",
            source="naver",
            source_name="에너지신문",
            published_at=now - timedelta(hours=2),
            category=None,
        ),
        # 중복 URL (제거 대상)
        NewsArticle(
            id="newsdata_001_dup",
            title="환경 정책 뉴스 (중복)",
            url="https://example.com/news/1",  # 중복 URL
            snippet="환경 관련 중복 기사입니다.",
            source="newsdata",
            source_name="다른매체",
            published_at=now - timedelta(minutes=30),
            category=None,
        ),
    ]


# ============================================================
# Mock Fixtures
# ============================================================


@pytest.fixture
def mock_news_cache() -> AsyncMock:
    """Mock NewsCachePort."""
    mock = AsyncMock()
    mock.is_fresh = AsyncMock(return_value=True)
    mock.get_articles = AsyncMock(return_value=([], None, False))
    mock.set_articles = AsyncMock()
    mock.get_total_count = AsyncMock(return_value=0)
    mock.get_ttl = AsyncMock(return_value=3600)
    return mock


@pytest.fixture
def mock_news_source() -> AsyncMock:
    """Mock NewsSourcePort."""
    mock = AsyncMock()
    mock.source_name = "mock_source"
    mock.fetch_news = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def mock_aggregator() -> MagicMock:
    """Mock NewsAggregatorService."""
    from info.application.services.news_aggregator import NewsAggregatorService

    return MagicMock(spec=NewsAggregatorService)


@pytest.fixture
def mock_og_extractor() -> AsyncMock:
    """Mock OGImageExtractor."""
    mock = AsyncMock()
    mock.enrich_articles_with_images = AsyncMock(side_effect=lambda x: x)
    return mock
