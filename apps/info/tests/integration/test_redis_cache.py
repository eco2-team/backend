"""Redis News Cache Integration Tests.

실제 Redis 연결이 필요한 통합 테스트.
CI 환경에서는 Redis 서비스가 필요합니다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from info.domain.entities import NewsArticle

# Redis가 없으면 테스트 스킵
pytest_plugins = ["pytest_asyncio"]


@pytest.fixture
def sample_articles_for_cache() -> list[NewsArticle]:
    """캐시 테스트용 샘플 기사."""
    now = datetime.now(timezone.utc)
    return [
        NewsArticle(
            id="article_001",
            title="First Article",
            url="https://example.com/1",
            snippet="First article content",
            source="naver",
            source_name="Test News",
            published_at=now,
            thumbnail_url="https://example.com/img1.jpg",
            category="environment",
        ),
        NewsArticle(
            id="article_002",
            title="Second Article",
            url="https://example.com/2",
            snippet="Second article content",
            source="newsdata",
            source_name="Global News",
            published_at=now - timedelta(hours=1),
            thumbnail_url=None,
            category="energy",
            keywords=("energy", "solar"),
        ),
        NewsArticle(
            id="article_003",
            title="Third Article",
            url="https://example.com/3",
            snippet="Third article content",
            source="naver",
            source_name="Tech News",
            published_at=now - timedelta(hours=2),
            category="ai",
            ai_tag="technology",
        ),
    ]


@pytest.mark.integration
@pytest.mark.asyncio
class TestRedisNewsCacheIntegration:
    """RedisNewsCache 통합 테스트.

    실제 Redis 연결 필요. 로컬 테스트 시:
    docker run -d -p 6379:6379 redis:7-alpine
    """

    @pytest.fixture
    async def redis_cache(self):
        """실제 Redis 연결 캐시."""
        import os

        from redis.asyncio import Redis

        from info.infrastructure.cache.redis_news_cache import RedisNewsCache

        redis_url = os.getenv("INFO_REDIS_URL", "redis://localhost:6379/1")

        try:
            redis = Redis.from_url(redis_url, decode_responses=True)
            await redis.ping()
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")

        cache = RedisNewsCache(redis=redis, ttl=60)

        # 테스트 전 클린업
        await redis.delete("news:feed:test_category")

        yield cache

        # 테스트 후 클린업
        keys = await redis.keys("news:*")
        if keys:
            await redis.delete(*keys)
        await redis.aclose()

    async def test_set_and_get_articles(
        self,
        redis_cache,
        sample_articles_for_cache: list[NewsArticle],
    ) -> None:
        """기사 저장 및 조회."""
        # Act
        await redis_cache.set_articles(
            category="test_category",
            articles=sample_articles_for_cache,
            ttl=60,
        )

        articles, next_cursor, has_more = await redis_cache.get_articles(
            category="test_category",
            cursor=None,
            limit=10,
        )

        # Assert
        assert len(articles) == 3
        assert articles[0].id == "article_001"  # 최신 먼저
        assert has_more is False

    async def test_pagination(
        self,
        redis_cache,
        sample_articles_for_cache: list[NewsArticle],
    ) -> None:
        """페이지네이션 테스트."""
        # Arrange
        await redis_cache.set_articles(
            category="test_category",
            articles=sample_articles_for_cache,
            ttl=60,
        )

        # Act - 첫 페이지 (1개만)
        articles, next_cursor, has_more = await redis_cache.get_articles(
            category="test_category",
            cursor=None,
            limit=1,
        )

        # Assert
        assert len(articles) == 1
        assert has_more is True
        assert next_cursor is not None

        # Act - 다음 페이지
        articles2, next_cursor2, has_more2 = await redis_cache.get_articles(
            category="test_category",
            cursor=next_cursor,
            limit=1,
        )

        # Assert
        assert len(articles2) == 1
        assert articles2[0].id != articles[0].id  # 다른 기사

    async def test_is_fresh(
        self,
        redis_cache,
        sample_articles_for_cache: list[NewsArticle],
    ) -> None:
        """캐시 freshness 확인."""
        # Act - 캐시 없을 때
        is_fresh_before = await redis_cache.is_fresh("test_category")

        # Assert
        assert is_fresh_before is False

        # Act - 캐시 저장 후
        await redis_cache.set_articles(
            category="test_category",
            articles=sample_articles_for_cache,
            ttl=60,
        )
        is_fresh_after = await redis_cache.is_fresh("test_category")

        # Assert
        assert is_fresh_after is True

    async def test_get_total_count(
        self,
        redis_cache,
        sample_articles_for_cache: list[NewsArticle],
    ) -> None:
        """총 기사 수 조회."""
        # Arrange
        await redis_cache.set_articles(
            category="test_category",
            articles=sample_articles_for_cache,
            ttl=60,
        )

        # Act
        count = await redis_cache.get_total_count("test_category")

        # Assert
        assert count == 3

    async def test_get_ttl(
        self,
        redis_cache,
        sample_articles_for_cache: list[NewsArticle],
    ) -> None:
        """TTL 조회."""
        # Arrange
        await redis_cache.set_articles(
            category="test_category",
            articles=sample_articles_for_cache,
            ttl=60,
        )

        # Act
        ttl = await redis_cache.get_ttl("test_category")

        # Assert
        assert 0 < ttl <= 60

    async def test_serialization_roundtrip(
        self,
        redis_cache,
    ) -> None:
        """직렬화/역직렬화 라운드트립."""
        # Arrange - 모든 필드가 있는 기사
        now = datetime.now(timezone.utc)
        full_article = NewsArticle(
            id="full_article",
            title="Full Article",
            url="https://example.com/full",
            snippet="Full article content",
            source="newsdata",
            source_name="Full News",
            published_at=now,
            thumbnail_url="https://example.com/thumb.jpg",
            category="environment",
            source_icon_url="https://example.com/icon.png",
            video_url="https://example.com/video.mp4",
            keywords=("keyword1", "keyword2"),
            ai_tag="environment_tag",
        )

        # Act
        await redis_cache.set_articles(
            category="test_category",
            articles=[full_article],
            ttl=60,
        )

        articles, _, _ = await redis_cache.get_articles(
            category="test_category",
            cursor=None,
            limit=10,
        )

        # Assert
        assert len(articles) == 1
        restored = articles[0]
        assert restored.id == full_article.id
        assert restored.title == full_article.title
        assert restored.thumbnail_url == full_article.thumbnail_url
        assert restored.source_icon_url == full_article.source_icon_url
        assert restored.video_url == full_article.video_url
        assert restored.keywords == full_article.keywords
        assert restored.ai_tag == full_article.ai_tag

    async def test_empty_category(self, redis_cache) -> None:
        """빈 카테고리 조회."""
        # Act
        articles, next_cursor, has_more = await redis_cache.get_articles(
            category="nonexistent_category",
            cursor=None,
            limit=10,
        )

        # Assert
        assert articles == []
        assert next_cursor is None
        assert has_more is False
