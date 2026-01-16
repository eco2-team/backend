"""FetchNewsCommand Unit Tests.

FetchNewsCommand는 Read-Only UseCase:
- Redis 캐시 조회 (Primary)
- Postgres Fallback (캐시 미스 시)
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from info.application.commands.fetch_news_command import FetchNewsCommand
from info.application.dto.news_request import NewsListRequest
from info.domain.entities import NewsArticle


class TestFetchNewsCommand:
    """FetchNewsCommand 테스트."""

    @pytest.fixture
    def command(
        self,
        mock_news_cache: AsyncMock,
    ) -> FetchNewsCommand:
        """FetchNewsCommand 인스턴스 (캐시만)."""
        return FetchNewsCommand(
            news_cache=mock_news_cache,
        )

    @pytest.fixture
    def command_with_fallback(
        self,
        mock_news_cache: AsyncMock,
        mock_news_repository: AsyncMock,
    ) -> FetchNewsCommand:
        """FetchNewsCommand 인스턴스 (캐시 + Postgres Fallback)."""
        return FetchNewsCommand(
            news_cache=mock_news_cache,
            news_repository=mock_news_repository,
        )

    @pytest.fixture
    def mock_news_repository(self) -> AsyncMock:
        """Mock NewsRepositoryPort."""
        mock = AsyncMock()
        mock.get_articles = AsyncMock()
        mock.get_total_count = AsyncMock(return_value=0)
        return mock

    @pytest.mark.asyncio
    async def test_returns_cached_articles(
        self,
        command: FetchNewsCommand,
        mock_news_cache: AsyncMock,
        sample_article: NewsArticle,
    ) -> None:
        """캐시에서 기사 반환."""
        # Arrange
        mock_news_cache.get_articles.return_value = ([sample_article], None, False)
        mock_news_cache.get_total_count.return_value = 1
        mock_news_cache.get_ttl.return_value = 3500

        request = NewsListRequest(category="all", limit=10)

        # Act
        result = await command.execute(request)

        # Assert
        assert len(result.articles) == 1
        assert result.articles[0].id == sample_article.id
        assert result.meta.source == "redis"

    @pytest.mark.asyncio
    async def test_fallback_to_postgres_on_cache_miss(
        self,
        command_with_fallback: FetchNewsCommand,
        mock_news_cache: AsyncMock,
        mock_news_repository: AsyncMock,
        sample_article: NewsArticle,
    ) -> None:
        """캐시 미스 시 Postgres Fallback."""
        from info.application.ports.news_repository import PaginatedResult

        # Arrange - 캐시 비어있음
        mock_news_cache.get_articles.return_value = ([], None, False)

        # Postgres 결과
        mock_news_repository.get_articles.return_value = PaginatedResult(
            articles=[sample_article],
            next_cursor=None,
            has_more=False,
            total_count=1,
            source="postgres",
        )
        mock_news_repository.get_total_count.return_value = 1

        request = NewsListRequest(category="all", limit=10)

        # Act
        result = await command_with_fallback.execute(request)

        # Assert
        assert len(result.articles) == 1
        mock_news_repository.get_articles.assert_called_once()
        assert result.meta.source == "postgres"

    @pytest.mark.asyncio
    async def test_filters_by_source(
        self,
        command: FetchNewsCommand,
        mock_news_cache: AsyncMock,
        now: datetime,
    ) -> None:
        """소스별 필터링 테스트."""
        # Arrange
        articles = [
            NewsArticle(
                id="naver_001",
                title="Naver Article",
                url="https://example.com/1",
                snippet="Test",
                source="naver",
                source_name="Test",
                published_at=now,
            ),
            NewsArticle(
                id="newsdata_001",
                title="NewsData Article",
                url="https://example.com/2",
                snippet="Test",
                source="newsdata",
                source_name="Test",
                published_at=now,
            ),
        ]

        mock_news_cache.get_articles.return_value = (articles, None, False)
        mock_news_cache.get_total_count.return_value = 2
        mock_news_cache.get_ttl.return_value = 3500

        request = NewsListRequest(category="all", limit=10, source="naver")

        # Act
        result = await command.execute(request)

        # Assert
        assert len(result.articles) == 1
        assert result.articles[0].source == "naver"

    @pytest.mark.asyncio
    async def test_filters_by_has_image(
        self,
        command: FetchNewsCommand,
        mock_news_cache: AsyncMock,
        now: datetime,
    ) -> None:
        """이미지 있는 기사만 필터링 테스트."""
        # Arrange
        articles = [
            NewsArticle(
                id="with_img",
                title="With Image",
                url="https://example.com/1",
                snippet="Test",
                source="naver",
                source_name="Test",
                published_at=now,
                thumbnail_url="https://example.com/img.jpg",
            ),
            NewsArticle(
                id="no_img",
                title="No Image",
                url="https://example.com/2",
                snippet="Test",
                source="naver",
                source_name="Test",
                published_at=now,
                thumbnail_url=None,
            ),
        ]

        mock_news_cache.get_articles.return_value = (articles, None, False)
        mock_news_cache.get_total_count.return_value = 2
        mock_news_cache.get_ttl.return_value = 3500

        request = NewsListRequest(category="all", limit=10, has_image=True)

        # Act
        result = await command.execute(request)

        # Assert
        assert len(result.articles) == 1
        assert result.articles[0].thumbnail_url is not None

    @pytest.mark.asyncio
    async def test_pagination_cursor(
        self,
        command: FetchNewsCommand,
        mock_news_cache: AsyncMock,
        sample_article: NewsArticle,
    ) -> None:
        """페이지네이션 커서 테스트."""
        # Arrange
        mock_news_cache.get_articles.return_value = (
            [sample_article],
            1234567890000,  # next_cursor
            True,  # has_more
        )
        mock_news_cache.get_total_count.return_value = 100
        mock_news_cache.get_ttl.return_value = 3500

        request = NewsListRequest(category="all", limit=10, cursor=1234567900000)

        # Act
        result = await command.execute(request)

        # Assert
        assert result.next_cursor == "1234567890000"
        assert result.has_more is True
        mock_news_cache.get_articles.assert_called_once_with(
            category="all",
            cursor=1234567900000,
            limit=10,
        )

    @pytest.mark.asyncio
    async def test_meta_information(
        self,
        command: FetchNewsCommand,
        mock_news_cache: AsyncMock,
        sample_article: NewsArticle,
    ) -> None:
        """메타 정보 반환 테스트."""
        # Arrange
        mock_news_cache.get_articles.return_value = ([sample_article], None, False)
        mock_news_cache.get_total_count.return_value = 150
        mock_news_cache.get_ttl.return_value = 2847

        request = NewsListRequest(category="environment", limit=10)

        # Act
        result = await command.execute(request)

        # Assert
        assert result.meta.total_cached == 150
        assert result.meta.cache_expires_in == 2847
        assert result.meta.source == "redis"

    @pytest.mark.asyncio
    async def test_empty_cache_without_fallback(
        self,
        command: FetchNewsCommand,
        mock_news_cache: AsyncMock,
    ) -> None:
        """캐시 비어있고 Fallback 없을 때 빈 결과."""
        # Arrange
        mock_news_cache.get_articles.return_value = ([], None, False)
        mock_news_cache.get_total_count.return_value = 0
        mock_news_cache.get_ttl.return_value = 0

        request = NewsListRequest(category="all", limit=10)

        # Act
        result = await command.execute(request)

        # Assert
        assert len(result.articles) == 0
        assert result.meta.source == "redis"
