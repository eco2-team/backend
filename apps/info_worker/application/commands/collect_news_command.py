"""Collect News Command.

뉴스 수집 UseCase (Write Path).
외부 API 호출 → Postgres 저장 → Redis 캐시 워밍.

gevent 호환을 위해 동기 코드로 작성.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from info.domain.constants import CATEGORIES

if TYPE_CHECKING:
    from info.application.services.news_aggregator import NewsAggregatorService
    from info.infrastructure.cache.redis_news_cache import RedisNewsCacheSync
    from info.infrastructure.integrations.og.og_image_extractor import OGImageExtractorSync
    from info_worker.application.ports.news_repository import NewsRepositoryPort
    from info_worker.application.ports.news_source import NewsSourcePort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollectNewsResult:
    """뉴스 수집 결과."""

    fetched: int  # API에서 가져온 기사 수
    unique: int  # 중복 제거 후
    saved: int  # Postgres 저장/갱신 수
    cached: int  # Redis 캐시 워밍 수
    with_images: int  # 이미지 있는 기사 수
    category: str


class CollectNewsCommand:
    """뉴스 수집 Command (Write UseCase).

    플로우:
    1. 외부 API 병렬 호출 (Naver, NewsData) - gevent Pool 사용
    2. 병합 및 중복 제거
    3. 카테고리 분류
    4. OG 이미지 추출 (선택)
    5. Postgres UPSERT
    6. Redis 캐시 워밍

    gevent 몽키패칭이 적용되면 동기 코드도 협력적 멀티태스킹.
    """

    def __init__(
        self,
        news_sources: list[NewsSourcePort],
        news_repository: NewsRepositoryPort,
        news_cache: RedisNewsCacheSync,
        aggregator: NewsAggregatorService,
        og_extractor: OGImageExtractorSync | None = None,
        cache_ttl: int = 3600,
        cache_warm_limit: int = 200,
    ):
        """초기화.

        Args:
            news_sources: 뉴스 소스 목록 (네이버, NewsData 등)
            news_repository: 뉴스 저장소 (Postgres)
            news_cache: 뉴스 캐시 (Redis, 동기)
            aggregator: 뉴스 집계 서비스
            og_extractor: OG 이미지 추출기 (동기, 선택)
            cache_ttl: 캐시 TTL (초)
            cache_warm_limit: 캐시 워밍 시 저장할 최대 기사 수
        """
        self._news_sources = news_sources
        self._news_repository = news_repository
        self._news_cache = news_cache
        self._aggregator = aggregator
        self._og_extractor = og_extractor
        self._cache_ttl = cache_ttl
        self._cache_warm_limit = cache_warm_limit

    def execute(self, category: str = "all") -> CollectNewsResult:
        """Command 실행 (동기).

        Args:
            category: 수집할 카테고리 ("all"이면 전체)

        Returns:
            수집 결과
        """
        logger.info("Starting news collection", extra={"category": category})

        # 1. 검색 쿼리 생성
        queries = self._aggregator.get_search_queries(category)

        # 2. 모든 소스에서 뉴스 가져오기
        all_articles = []

        for query in queries:
            # gevent Pool로 병렬 처리 시도
            try:
                from gevent.pool import Pool

                pool = Pool(len(self._news_sources))

                def fetch_from_source(source):
                    try:
                        return source.fetch_news(query=query, max_results=30)
                    except Exception as e:
                        logger.warning("News source failed: %s", e)
                        return []

                results = pool.map(fetch_from_source, self._news_sources)
            except ImportError:
                # gevent 없으면 순차 처리
                logger.debug("gevent not available, sequential fetch")
                results = []
                for source in self._news_sources:
                    try:
                        result = source.fetch_news(query=query, max_results=30)
                        results.append(result)
                    except Exception as e:
                        logger.warning("News source failed: %s", e)
                        results.append([])

            for result in results:
                if result:
                    all_articles.extend(result)

        fetched_count = len(all_articles)

        if not all_articles:
            logger.warning("No articles fetched from any source")
            return CollectNewsResult(
                fetched=0,
                unique=0,
                saved=0,
                cached=0,
                with_images=0,
                category=category,
            )

        # 3. 병합 및 중복 제거
        unique_articles = self._aggregator.merge_and_deduplicate(all_articles)

        # 4. 카테고리 분류
        classified_articles = self._aggregator.classify_articles(unique_articles)

        # 5. OG 이미지 추출 (이미지 없는 기사 보강)
        if self._og_extractor:
            classified_articles = self._og_extractor.enrich_articles_with_images(
                classified_articles
            )

        # 6. 이미지 있는 기사 우선 정렬
        prioritized_articles = self._aggregator.prioritize_with_images(classified_articles)

        # 7. Postgres UPSERT
        saved_count = self._news_repository.upsert_articles(prioritized_articles)

        # 8. Redis 캐시 워밍
        cached_count = self._warm_cache(category)

        # 통계
        with_images = sum(1 for a in prioritized_articles if a.thumbnail_url)

        logger.info(
            "News collection completed",
            extra={
                "category": category,
                "fetched": fetched_count,
                "unique": len(prioritized_articles),
                "saved": saved_count,
                "cached": cached_count,
                "with_images": with_images,
            },
        )

        return CollectNewsResult(
            fetched=fetched_count,
            unique=len(prioritized_articles),
            saved=saved_count,
            cached=cached_count,
            with_images=with_images,
            category=category,
        )

    def _warm_cache(self, category: str) -> int:
        """Redis 캐시 워밍 (동기).

        Postgres에서 최근 기사를 조회하여 Redis에 캐싱.

        Args:
            category: 카테고리

        Returns:
            캐시된 기사 수
        """
        # Postgres에서 최근 기사 조회
        recent_articles = self._news_repository.get_recent_articles(
            category="all",  # 전체 기사 기준
            limit=self._cache_warm_limit,
        )

        if not recent_articles:
            return 0

        # "all" 카테고리에 전체 저장
        self._news_cache.set_articles(
            category="all",
            articles=recent_articles,
            ttl=self._cache_ttl,
        )

        # 개별 카테고리별로도 저장
        for cat in CATEGORIES:
            filtered = self._aggregator.filter_by_category(recent_articles, cat)
            if filtered:
                self._news_cache.set_articles(
                    category=cat,
                    articles=filtered,
                    ttl=self._cache_ttl,
                )

        logger.info(
            "Cache warming completed",
            extra={
                "total_articles": len(recent_articles),
                "ttl": self._cache_ttl,
            },
        )

        return len(recent_articles)
