"""News Aggregator Service.

여러 뉴스 소스의 결과를 병합하고 분류하는 서비스.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from info.domain.constants import CATEGORY_KEYWORDS

if TYPE_CHECKING:
    from info.domain.entities import NewsArticle

logger = logging.getLogger(__name__)


class NewsAggregatorService:
    """뉴스 병합/분류 서비스.

    정책:
    1. URL 기반 중복 제거
    2. 시간순 정렬 (최신 먼저)
    3. 키워드 기반 카테고리 분류
    """

    @staticmethod
    def merge_and_deduplicate(
        articles: list[NewsArticle],
    ) -> list[NewsArticle]:
        """기사 목록을 중복 제거.

        Args:
            articles: 기사 목록

        Returns:
            중복 제거된 기사 목록 (시간순 정렬)
        """
        # URL 기반 중복 제거
        seen_urls: set[str] = set()
        unique_articles: list[NewsArticle] = []

        for article in articles:
            if article.url not in seen_urls:
                seen_urls.add(article.url)
                unique_articles.append(article)

        # 시간순 정렬 (최신 먼저)
        unique_articles.sort(key=lambda a: a.published_at, reverse=True)

        logger.debug(
            "Merged articles",
            extra={
                "total_input": len(articles),
                "unique_output": len(unique_articles),
            },
        )

        return unique_articles

    # NewsData.io 카테고리 → 내부 카테고리 매핑
    NEWSDATA_CATEGORY_MAP: dict[str, str] = {
        # environment
        "environment": "environment",
        "world": "environment",
        "lifestyle": "environment",
        # energy
        "business": "energy",
        "science": "energy",
        # ai/tech
        "technology": "ai",
        "top": "ai",
    }

    @staticmethod
    def classify_article(article: NewsArticle) -> str:
        """기사 카테고리 분류.

        우선순위:
        1. NewsData.io 자체 카테고리 (매핑 가능한 경우)
        2. AI 태그 기반 분류
        3. 키워드 매칭 기반 분류

        Args:
            article: 뉴스 기사

        Returns:
            카테고리 ("environment", "energy", "ai")
        """
        # 1. NewsData 카테고리 매핑 시도
        if article.category:
            # NewsData는 카테고리를 리스트로 반환함
            if isinstance(article.category, list):
                newsdata_cat = article.category[0].strip().lower() if article.category else ""
            else:
                newsdata_cat = article.category.split(",")[0].strip().lower()
            if newsdata_cat in NewsAggregatorService.NEWSDATA_CATEGORY_MAP:
                return NewsAggregatorService.NEWSDATA_CATEGORY_MAP[newsdata_cat]

        # 2. AI 태그 기반 분류 (있으면)
        if article.ai_tag:
            ai_tag_lower = article.ai_tag.lower()
            if any(kw in ai_tag_lower for kw in ["환경", "climate", "recycle", "waste"]):
                return "environment"
            if any(kw in ai_tag_lower for kw in ["energy", "에너지", "solar", "전기"]):
                return "energy"
            if any(kw in ai_tag_lower for kw in ["ai", "인공지능", "tech", "gpt"]):
                return "ai"

        # 3. 키워드 매칭 기반 분류
        text = f"{article.title} {article.snippet}".lower()

        scores: dict[str, int] = {}
        for category, keywords in CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in text)
            scores[category] = score

        # 점수가 가장 높은 카테고리 선택
        if max(scores.values()) == 0:
            return "environment"  # 기본 카테고리

        return max(scores, key=lambda k: scores[k])

    @staticmethod
    def classify_articles(articles: list[NewsArticle]) -> list[NewsArticle]:
        """기사 목록 카테고리 분류.

        Args:
            articles: 뉴스 기사 목록

        Returns:
            카테고리가 설정된 기사 목록
        """
        return [
            article.with_category(NewsAggregatorService.classify_article(article))
            for article in articles
        ]

    @staticmethod
    def filter_by_category(
        articles: list[NewsArticle],
        category: str,
    ) -> list[NewsArticle]:
        """카테고리별 필터링.

        Args:
            articles: 뉴스 기사 목록
            category: 카테고리 ("all"이면 전체)

        Returns:
            필터링된 기사 목록
        """
        if category == "all":
            return articles

        return [a for a in articles if a.category == category]

    @staticmethod
    def prioritize_with_images(
        articles: list[NewsArticle],
    ) -> list[NewsArticle]:
        """이미지가 있는 기사를 우선 정렬.

        Perplexity 스타일 UI를 위해 썸네일이 있는 기사를 앞으로 배치.
        각 그룹 내에서는 시간순 정렬 유지.

        Args:
            articles: 뉴스 기사 목록

        Returns:
            이미지 우선 정렬된 기사 목록
        """
        with_image = [a for a in articles if a.thumbnail_url]
        without_image = [a for a in articles if not a.thumbnail_url]

        # 각 그룹 내에서 시간순 정렬 유지
        with_image.sort(key=lambda a: a.published_at, reverse=True)
        without_image.sort(key=lambda a: a.published_at, reverse=True)

        return with_image + without_image

    @staticmethod
    def get_search_queries(category: str) -> list[str]:
        """카테고리별 검색 쿼리 생성.

        한국어 쿼리(네이버용)와 영어 쿼리(NewsData.io용)를 모두 반환.

        Args:
            category: 카테고리

        Returns:
            검색 쿼리 목록 (한국어 + 영어)
        """
        # 카테고리별 쿼리 (한국어, 영어)
        query_map = {
            "all": [
                "환경 분리배출 재활용",  # 네이버용
                "environment recycling waste",  # NewsData용
                "renewable energy climate",
            ],
            "environment": [
                "환경 분리배출 재활용",
                "environment recycling climate change",
            ],
            "energy": [
                "신재생에너지 탄소중립 태양광",
                "renewable energy solar EV battery",
            ],
            "ai": [
                "인공지능 AI 환경",
                "AI artificial intelligence technology",
            ],
        }

        return query_map.get(category, query_map["all"])
