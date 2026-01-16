"""NewsAggregatorService Unit Tests."""

from __future__ import annotations

from datetime import datetime, timedelta


from info.application.services.news_aggregator import NewsAggregatorService
from info.domain.entities import NewsArticle


class TestMergeAndDeduplicate:
    """merge_and_deduplicate 메서드 테스트."""

    def test_removes_duplicate_urls(self, sample_articles: list[NewsArticle]) -> None:
        """URL 기반 중복 제거 테스트."""
        # Act
        result = NewsAggregatorService.merge_and_deduplicate(sample_articles)

        # Assert
        urls = [a.url for a in result]
        assert len(urls) == len(set(urls)), "중복 URL이 있으면 안됨"
        assert len(result) == 3  # 4개 중 1개 중복 제거

    def test_sorts_by_published_at_desc(self, now: datetime) -> None:
        """시간순 정렬 (최신 먼저) 테스트."""
        # Arrange
        articles = [
            NewsArticle(
                id="old",
                title="Old",
                url="https://example.com/old",
                snippet="Old article",
                source="naver",
                source_name="Test",
                published_at=now - timedelta(hours=2),
            ),
            NewsArticle(
                id="new",
                title="New",
                url="https://example.com/new",
                snippet="New article",
                source="naver",
                source_name="Test",
                published_at=now,
            ),
            NewsArticle(
                id="mid",
                title="Mid",
                url="https://example.com/mid",
                snippet="Mid article",
                source="naver",
                source_name="Test",
                published_at=now - timedelta(hours=1),
            ),
        ]

        # Act
        result = NewsAggregatorService.merge_and_deduplicate(articles)

        # Assert
        assert result[0].id == "new"
        assert result[1].id == "mid"
        assert result[2].id == "old"

    def test_empty_list(self) -> None:
        """빈 리스트 처리 테스트."""
        result = NewsAggregatorService.merge_and_deduplicate([])
        assert result == []

    def test_single_article(self, sample_article: NewsArticle) -> None:
        """단일 기사 처리 테스트."""
        result = NewsAggregatorService.merge_and_deduplicate([sample_article])
        assert len(result) == 1
        assert result[0].id == sample_article.id


class TestClassifyArticle:
    """classify_article 메서드 테스트."""

    def test_environment_keywords(self, now: datetime) -> None:
        """환경 키워드 분류 테스트."""
        article = NewsArticle(
            id="env",
            title="환경부 분리배출 정책",
            url="https://example.com/env",
            snippet="재활용 쓰레기 처리",
            source="naver",
            source_name="Test",
            published_at=now,
        )

        result = NewsAggregatorService.classify_article(article)
        assert result == "environment"

    def test_energy_keywords(self, now: datetime) -> None:
        """에너지 키워드 분류 테스트."""
        article = NewsArticle(
            id="energy",
            title="신재생에너지 태양광 발전",
            url="https://example.com/energy",
            snippet="전기차 배터리 기술",
            source="naver",
            source_name="Test",
            published_at=now,
        )

        result = NewsAggregatorService.classify_article(article)
        assert result == "energy"

    def test_ai_keywords(self, now: datetime) -> None:
        """AI 키워드 분류 테스트."""
        article = NewsArticle(
            id="ai",
            title="인공지능 AI 기술 발전",
            url="https://example.com/ai",
            snippet="GPT LLM 머신러닝",
            source="naver",
            source_name="Test",
            published_at=now,
        )

        result = NewsAggregatorService.classify_article(article)
        assert result == "ai"

    def test_newsdata_category_mapping(self, now: datetime) -> None:
        """NewsData 카테고리 매핑 테스트."""
        article = NewsArticle(
            id="newsdata",
            title="Technology News",
            url="https://example.com/tech",
            snippet="Some tech news",
            source="newsdata",
            source_name="TechCrunch",
            published_at=now,
            category="technology",  # NewsData 카테고리
        )

        result = NewsAggregatorService.classify_article(article)
        assert result == "ai"  # technology -> ai

    def test_ai_tag_classification(self, now: datetime) -> None:
        """AI 태그 기반 분류 테스트."""
        article = NewsArticle(
            id="tagged",
            title="Some News",
            url="https://example.com/tagged",
            snippet="Generic content",
            source="newsdata",
            source_name="News",
            published_at=now,
            ai_tag="climate change",
        )

        result = NewsAggregatorService.classify_article(article)
        assert result == "environment"

    def test_default_category(self, now: datetime) -> None:
        """기본 카테고리 (매칭 없을 때) 테스트."""
        article = NewsArticle(
            id="generic",
            title="일반 뉴스",
            url="https://example.com/generic",
            snippet="아무 키워드도 없는 기사",
            source="naver",
            source_name="Test",
            published_at=now,
        )

        result = NewsAggregatorService.classify_article(article)
        assert result == "environment"  # 기본값


class TestClassifyArticles:
    """classify_articles 메서드 테스트."""

    def test_classifies_all_articles(self, sample_articles: list[NewsArticle]) -> None:
        """모든 기사 분류 테스트."""
        # Act
        result = NewsAggregatorService.classify_articles(sample_articles)

        # Assert
        assert len(result) == len(sample_articles)
        for article in result:
            assert article.category in ["environment", "energy", "ai"]


class TestFilterByCategory:
    """filter_by_category 메서드 테스트."""

    def test_filter_all_returns_everything(self, now: datetime) -> None:
        """'all' 필터는 전체 반환."""
        articles = [
            NewsArticle(
                id="1",
                title="Test",
                url="https://example.com/1",
                snippet="Test",
                source="naver",
                source_name="Test",
                published_at=now,
                category="environment",
            ),
            NewsArticle(
                id="2",
                title="Test",
                url="https://example.com/2",
                snippet="Test",
                source="naver",
                source_name="Test",
                published_at=now,
                category="ai",
            ),
        ]

        result = NewsAggregatorService.filter_by_category(articles, "all")
        assert len(result) == 2

    def test_filter_specific_category(self, now: datetime) -> None:
        """특정 카테고리 필터 테스트."""
        articles = [
            NewsArticle(
                id="1",
                title="Test",
                url="https://example.com/1",
                snippet="Test",
                source="naver",
                source_name="Test",
                published_at=now,
                category="environment",
            ),
            NewsArticle(
                id="2",
                title="Test",
                url="https://example.com/2",
                snippet="Test",
                source="naver",
                source_name="Test",
                published_at=now,
                category="ai",
            ),
        ]

        result = NewsAggregatorService.filter_by_category(articles, "environment")
        assert len(result) == 1
        assert result[0].category == "environment"


class TestPrioritizeWithImages:
    """prioritize_with_images 메서드 테스트."""

    def test_images_first(self, now: datetime) -> None:
        """이미지 있는 기사 우선 정렬 테스트."""
        articles = [
            NewsArticle(
                id="no_img",
                title="No Image",
                url="https://example.com/1",
                snippet="Test",
                source="naver",
                source_name="Test",
                published_at=now,
                thumbnail_url=None,
            ),
            NewsArticle(
                id="has_img",
                title="Has Image",
                url="https://example.com/2",
                snippet="Test",
                source="naver",
                source_name="Test",
                published_at=now - timedelta(hours=1),
                thumbnail_url="https://example.com/img.jpg",
            ),
        ]

        result = NewsAggregatorService.prioritize_with_images(articles)

        assert result[0].id == "has_img"  # 이미지 있는 것이 먼저
        assert result[1].id == "no_img"

    def test_maintains_time_order_within_groups(self, now: datetime) -> None:
        """각 그룹 내에서 시간순 정렬 유지."""
        articles = [
            NewsArticle(
                id="img_old",
                title="Old with image",
                url="https://example.com/1",
                snippet="Test",
                source="naver",
                source_name="Test",
                published_at=now - timedelta(hours=2),
                thumbnail_url="https://example.com/img1.jpg",
            ),
            NewsArticle(
                id="img_new",
                title="New with image",
                url="https://example.com/2",
                snippet="Test",
                source="naver",
                source_name="Test",
                published_at=now,
                thumbnail_url="https://example.com/img2.jpg",
            ),
            NewsArticle(
                id="no_img",
                title="No image",
                url="https://example.com/3",
                snippet="Test",
                source="naver",
                source_name="Test",
                published_at=now - timedelta(hours=1),
                thumbnail_url=None,
            ),
        ]

        result = NewsAggregatorService.prioritize_with_images(articles)

        # 이미지 있는 그룹: 최신 먼저
        assert result[0].id == "img_new"
        assert result[1].id == "img_old"
        # 이미지 없는 그룹
        assert result[2].id == "no_img"


class TestGetSearchQueries:
    """get_search_queries 메서드 테스트."""

    def test_all_category(self) -> None:
        """'all' 카테고리 쿼리."""
        queries = NewsAggregatorService.get_search_queries("all")
        assert len(queries) >= 2
        assert any("환경" in q for q in queries)  # 한국어 쿼리 포함
        assert any("environment" in q for q in queries)  # 영어 쿼리 포함

    def test_environment_category(self) -> None:
        """'environment' 카테고리 쿼리."""
        queries = NewsAggregatorService.get_search_queries("environment")
        assert any("환경" in q or "분리배출" in q for q in queries)

    def test_energy_category(self) -> None:
        """'energy' 카테고리 쿼리."""
        queries = NewsAggregatorService.get_search_queries("energy")
        assert any("에너지" in q or "energy" in q for q in queries)

    def test_ai_category(self) -> None:
        """'ai' 카테고리 쿼리."""
        queries = NewsAggregatorService.get_search_queries("ai")
        assert any("AI" in q or "인공지능" in q for q in queries)

    def test_unknown_category_falls_back_to_all(self) -> None:
        """알 수 없는 카테고리는 'all'로 폴백."""
        queries = NewsAggregatorService.get_search_queries("unknown")
        all_queries = NewsAggregatorService.get_search_queries("all")
        assert queries == all_queries
