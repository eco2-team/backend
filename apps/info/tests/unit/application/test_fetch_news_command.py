"""FetchNewsCommand Unit Tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

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
        mock_news_source: AsyncMock,
        mock_aggregator: MagicMock,
        mock_og_extractor: AsyncMock,
    ) -> FetchNewsCommand:
        """FetchNewsCommand 인스턴스."""
        return FetchNewsCommand(
            news_sources=[mock_news_source],
            news_cache=mock_news_cache,
            aggregator=mock_aggregator,
            cache_ttl=3600,
            og_extractor=mock_og_extractor,
        )

    @pytest.mark.asyncio
    async def test_returns_cached_articles_when_fresh(
        self,
        command: FetchNewsCommand,
        mock_news_cache: AsyncMock,
        sample_article: NewsArticle,
    ) -> None:
        """캐시가 fresh일 때 캐시된 기사 반환."""
        # Arrange
        mock_news_cache.is_fresh.return_value = True
        mock_news_cache.get_articles.return_value = ([sample_article], None, False)
        mock_news_cache.get_total_count.return_value = 1
        mock_news_cache.get_ttl.return_value = 3500

        request = NewsListRequest(category="all", limit=10)

        # Act
        result = await command.execute(request)

        # Assert
        assert len(result.articles) == 1
        assert result.articles[0].id == sample_article.id
        mock_news_cache.is_fresh.assert_called_once_with("all")

    @pytest.mark.asyncio
    async def test_refreshes_cache_when_stale(
        self,
        command: FetchNewsCommand,
        mock_news_cache: AsyncMock,
        mock_news_source: AsyncMock,
        mock_aggregator: MagicMock,
        sample_article: NewsArticle,
        now: datetime,
    ) -> None:
        """캐시가 stale일 때 외부 API 호출."""
        # Arrange
        mock_news_cache.is_fresh.return_value = False
        mock_news_cache.get_articles.return_value = ([sample_article], None, False)
        mock_news_cache.get_total_count.return_value = 1
        mock_news_cache.get_ttl.return_value = 3600

        # 외부 API 응답 설정
        fetched_article = NewsArticle(
            id="fetched_001",
            title="Fetched Article",
            url="https://example.com/fetched",
            snippet="Fetched content",
            source="mock_source",
            source_name="Test",
            published_at=now,
        )
        mock_news_source.fetch_news.return_value = [fetched_article]

        # Aggregator 설정
        mock_aggregator.get_search_queries.return_value = ["test query"]
        mock_aggregator.merge_and_deduplicate.return_value = [fetched_article]
        mock_aggregator.classify_articles.return_value = [
            fetched_article.with_category("environment")
        ]
        mock_aggregator.prioritize_with_images.return_value = [
            fetched_article.with_category("environment")
        ]
        mock_aggregator.filter_by_category.return_value = [
            fetched_article.with_category("environment")
        ]

        request = NewsListRequest(category="all", limit=10)

        # Act
        await command.execute(request)

        # Assert
        mock_news_source.fetch_news.assert_called()
        mock_news_cache.set_articles.assert_called()

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

        mock_news_cache.is_fresh.return_value = True
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

        mock_news_cache.is_fresh.return_value = True
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
        mock_news_cache.is_fresh.return_value = True
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
        mock_news_cache.is_fresh.return_value = True
        mock_news_cache.get_articles.return_value = ([sample_article], None, False)
        mock_news_cache.get_total_count.return_value = 150
        mock_news_cache.get_ttl.return_value = 2847

        request = NewsListRequest(category="environment", limit=10)

        # Act
        result = await command.execute(request)

        # Assert
        assert result.meta.total_cached == 150
        assert result.meta.cache_expires_in == 2847

    @pytest.mark.asyncio
    async def test_handles_api_failure_gracefully(
        self,
        command: FetchNewsCommand,
        mock_news_cache: AsyncMock,
        mock_news_source: AsyncMock,
        mock_aggregator: MagicMock,
    ) -> None:
        """외부 API 실패 시 graceful 처리."""
        # Arrange
        mock_news_cache.is_fresh.return_value = False
        mock_news_cache.get_articles.return_value = ([], None, False)
        mock_news_cache.get_total_count.return_value = 0
        mock_news_cache.get_ttl.return_value = 0

        # API 실패 시뮬레이션
        mock_news_source.fetch_news.side_effect = Exception("API Error")
        mock_aggregator.get_search_queries.return_value = ["test query"]

        request = NewsListRequest(category="all", limit=10)

        # Act
        result = await command.execute(request)

        # Assert - 예외 없이 빈 결과 반환
        assert len(result.articles) == 0

    @pytest.mark.asyncio
    async def test_no_news_sources_configured(
        self,
        mock_news_cache: AsyncMock,
        mock_aggregator: MagicMock,
    ) -> None:
        """뉴스 소스가 없을 때 테스트."""
        # Arrange
        command = FetchNewsCommand(
            news_sources=[],  # 빈 소스 목록
            news_cache=mock_news_cache,
            aggregator=mock_aggregator,
            cache_ttl=3600,
        )

        mock_news_cache.is_fresh.return_value = False
        mock_news_cache.get_articles.return_value = ([], None, False)
        mock_news_cache.get_total_count.return_value = 0
        mock_news_cache.get_ttl.return_value = 0
        mock_aggregator.get_search_queries.return_value = ["test"]

        request = NewsListRequest(category="all", limit=10)

        # Act
        result = await command.execute(request)

        # Assert
        assert len(result.articles) == 0
