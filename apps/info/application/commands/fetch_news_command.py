"""Fetch News Command (Read-Only).

뉴스 조회 UseCase.
Redis 캐시 → Postgres Fallback 순으로 조회.

3-Tier Architecture에서 API는 읽기만 담당:
- 쓰기(수집): info_worker
- 읽기(조회): info API (이 모듈)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from info.application.dto.news_request import NewsListRequest
from info.application.dto.news_response import (
    NewsArticleResponse,
    NewsListResponse,
    NewsMeta,
)
from info.application.ports.news_repository import NewsCursor

if TYPE_CHECKING:
    from info.application.ports.news_cache import NewsCachePort
    from info.application.ports.news_repository import NewsRepositoryPort

logger = logging.getLogger(__name__)


class FetchNewsCommand:
    """뉴스 조회 Command (ReadOnly UseCase).

    플로우:
    1. Redis 캐시 조회 (Primary)
    2. 캐시 미스 → Postgres Fallback
    3. 응답 반환

    Write Path는 info_worker가 담당:
    - Celery Beat → API 호출 → Postgres UPSERT → Redis 캐시 워밍
    """

    def __init__(
        self,
        news_cache: NewsCachePort,
        news_repository: NewsRepositoryPort | None = None,
    ):
        """초기화.

        Args:
            news_cache: 뉴스 캐시 (Redis)
            news_repository: 뉴스 저장소 (Postgres, Fallback용)
        """
        self._news_cache = news_cache
        self._news_repository = news_repository

    async def execute(self, request: NewsListRequest) -> NewsListResponse:
        """Command 실행.

        Args:
            request: 뉴스 목록 요청

        Returns:
            뉴스 목록 응답
        """
        category = request.category
        source_used = "redis"

        # 1. Redis 캐시 조회 (Primary)
        articles, next_cursor, has_more = await self._news_cache.get_articles(
            category=category,
            cursor=request.cursor,
            limit=request.limit,
        )

        # 2. 캐시 미스 → Postgres Fallback
        if not articles and self._news_repository:
            logger.info(
                "Cache miss, falling back to Postgres",
                extra={"category": category},
            )
            source_used = "postgres"

            # 커서 변환 (int → NewsCursor)
            cursor = None
            if request.cursor:
                # 기존 형식 (timestamp only) → 새 형식 (timestamp_id)
                # Fallback: cursor가 숫자면 timestamp로 해석
                if "_" in str(request.cursor):
                    cursor = NewsCursor.decode(str(request.cursor))
                else:
                    # 레거시 cursor (timestamp만) - ID 없이 조회
                    from datetime import datetime, timezone

                    ts = datetime.fromtimestamp(int(request.cursor) / 1000, tz=timezone.utc)
                    cursor = NewsCursor(published_at=ts, article_id="")

            result = await self._news_repository.get_articles(
                category=category,
                cursor=cursor,
                limit=request.limit,
            )
            articles = result.articles
            has_more = result.has_more
            next_cursor = result.next_cursor.encode() if result.next_cursor else None

        # 3. 소스 필터링 (요청된 경우)
        if request.source != "all":
            articles = [a for a in articles if a.source == request.source]

        # 4. 이미지 필터링 (요청된 경우)
        if request.has_image:
            articles = [a for a in articles if a.thumbnail_url]

        # 5. 메타 정보 조회
        if source_used == "redis":
            total_cached = await self._news_cache.get_total_count(category)
            cache_ttl = await self._news_cache.get_ttl(category)
        else:
            total_cached = await self._news_repository.get_total_count(category)
            cache_ttl = 0  # Postgres에서 가져온 경우 TTL 없음

        # 6. 응답 생성
        return NewsListResponse(
            articles=[NewsArticleResponse.from_entity(a) for a in articles],
            next_cursor=str(next_cursor) if next_cursor else None,
            has_more=has_more,
            meta=NewsMeta(
                total_cached=total_cached,
                cache_expires_in=cache_ttl,
                source=source_used,
            ),
        )
