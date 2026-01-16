"""Postgres News Repository.

PostgreSQL을 사용한 뉴스 저장소 구현.
asyncpg를 사용하여 비동기 I/O 지원.
"""

from __future__ import annotations

import logging
from datetime import timezone
from typing import TYPE_CHECKING

from info_worker.application.ports.news_repository import (
    NewsCursor,
    NewsRepositoryPort,
    PaginatedResult,
)
from info_worker.domain.entities import NewsArticle

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)


class PostgresNewsRepository(NewsRepositoryPort):
    """PostgreSQL 뉴스 저장소.

    asyncpg를 사용하여 비동기 I/O 지원.
    UPSERT로 중복 처리, 커서 기반 페이지네이션 지원.
    """

    def __init__(self, pool: asyncpg.Pool):
        """초기화.

        Args:
            pool: asyncpg connection pool
        """
        self._pool = pool

    async def upsert_articles(self, articles: list[NewsArticle]) -> int:
        """기사 일괄 저장 (UPSERT).

        INSERT ... ON CONFLICT (url) DO UPDATE로 중복 처리.
        """
        if not articles:
            return 0

        # UPSERT 쿼리
        query = """
            INSERT INTO info.news_articles (
                id, url, title, snippet,
                source, source_name, source_icon_url,
                thumbnail_url, video_url,
                category, keywords, ai_tag,
                published_at, created_at, updated_at
            )
            SELECT
                unnest($1::varchar[]),
                unnest($2::text[]),
                unnest($3::text[]),
                unnest($4::text[]),
                unnest($5::varchar[]),
                unnest($6::varchar[]),
                unnest($7::text[]),
                unnest($8::text[]),
                unnest($9::text[]),
                unnest($10::varchar[]),
                unnest($11::text[][]),
                unnest($12::varchar[]),
                unnest($13::timestamptz[]),
                NOW(),
                NOW()
            ON CONFLICT (url) DO UPDATE SET
                title = EXCLUDED.title,
                snippet = EXCLUDED.snippet,
                thumbnail_url = COALESCE(EXCLUDED.thumbnail_url, info.news_articles.thumbnail_url),
                video_url = COALESCE(EXCLUDED.video_url, info.news_articles.video_url),
                keywords = COALESCE(EXCLUDED.keywords, info.news_articles.keywords),
                ai_tag = COALESCE(EXCLUDED.ai_tag, info.news_articles.ai_tag),
                updated_at = NOW()
            WHERE info.news_articles.is_deleted = FALSE
        """

        # 배열 준비
        ids = [a.id for a in articles]
        urls = [a.url for a in articles]
        titles = [a.title for a in articles]
        snippets = [a.snippet for a in articles]
        sources = [a.source for a in articles]
        source_names = [a.source_name for a in articles]
        source_icon_urls = [a.source_icon_url for a in articles]
        thumbnail_urls = [a.thumbnail_url for a in articles]
        video_urls = [a.video_url for a in articles]
        categories = [a.category or "all" for a in articles]
        keywords_list = [list(a.keywords) if a.keywords else None for a in articles]
        ai_tags = [a.ai_tag for a in articles]
        published_ats = [a.published_at for a in articles]

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                query,
                ids,
                urls,
                titles,
                snippets,
                sources,
                source_names,
                source_icon_urls,
                thumbnail_urls,
                video_urls,
                categories,
                keywords_list,
                ai_tags,
                published_ats,
            )

            # "INSERT 0 N" 형식에서 N 추출
            count = int(result.split()[-1])

            logger.info(
                "Upserted news articles",
                extra={"count": count, "total": len(articles)},
            )

            return count

    async def get_articles(
        self,
        category: str,
        cursor: NewsCursor | None = None,
        limit: int = 20,
    ) -> PaginatedResult:
        """카테고리별 기사 조회 (커서 기반 페이지네이션)."""
        async with self._pool.acquire() as conn:
            if cursor is None:
                # 첫 페이지 (커서 없음)
                if category == "all":
                    query = """
                        SELECT * FROM info.news_articles
                        WHERE is_deleted = FALSE
                        ORDER BY published_at DESC, id DESC
                        LIMIT $1
                    """
                    rows = await conn.fetch(query, limit + 1)
                else:
                    query = """
                        SELECT * FROM info.news_articles
                        WHERE category = $1 AND is_deleted = FALSE
                        ORDER BY published_at DESC, id DESC
                        LIMIT $2
                    """
                    rows = await conn.fetch(query, category, limit + 1)
            else:
                # 다음 페이지 (커서 사용)
                if category == "all":
                    query = """
                        SELECT * FROM info.news_articles
                        WHERE is_deleted = FALSE
                          AND (published_at, id) < ($1, $2)
                        ORDER BY published_at DESC, id DESC
                        LIMIT $3
                    """
                    rows = await conn.fetch(
                        query, cursor.published_at, cursor.article_id, limit + 1
                    )
                else:
                    query = """
                        SELECT * FROM info.news_articles
                        WHERE category = $1 AND is_deleted = FALSE
                          AND (published_at, id) < ($2, $3)
                        ORDER BY published_at DESC, id DESC
                        LIMIT $4
                    """
                    rows = await conn.fetch(
                        query,
                        category,
                        cursor.published_at,
                        cursor.article_id,
                        limit + 1,
                    )

            # has_more 판단
            has_more = len(rows) > limit
            if has_more:
                rows = rows[:limit]

            # 엔티티 변환
            articles = [self._row_to_entity(row) for row in rows]

            # 다음 커서
            next_cursor = None
            if articles and has_more:
                last = articles[-1]
                next_cursor = NewsCursor(published_at=last.published_at, article_id=last.id)

            # 총 개수 (첫 페이지에서만 조회, 이후는 -1로 반환)
            # 성능 최적화: COUNT(*)는 비용이 높으므로 첫 페이지에서만
            total_count = -1
            if cursor is None:
                total_count = await self.get_total_count(category)

            return PaginatedResult(
                articles=articles,
                next_cursor=next_cursor,
                has_more=has_more,
                total_count=total_count,
            )

    async def get_recent_articles(
        self,
        category: str,
        limit: int = 200,
    ) -> list[NewsArticle]:
        """최근 기사 조회 (캐시 워밍용)."""
        async with self._pool.acquire() as conn:
            if category == "all":
                query = """
                    SELECT * FROM info.news_articles
                    WHERE is_deleted = FALSE
                    ORDER BY published_at DESC
                    LIMIT $1
                """
                rows = await conn.fetch(query, limit)
            else:
                query = """
                    SELECT * FROM info.news_articles
                    WHERE category = $1 AND is_deleted = FALSE
                    ORDER BY published_at DESC
                    LIMIT $2
                """
                rows = await conn.fetch(query, category, limit)

            return [self._row_to_entity(row) for row in rows]

    async def get_total_count(self, category: str) -> int:
        """카테고리별 기사 총 개수."""
        async with self._pool.acquire() as conn:
            if category == "all":
                query = """
                    SELECT COUNT(*) FROM info.news_articles
                    WHERE is_deleted = FALSE
                """
                return await conn.fetchval(query)
            else:
                query = """
                    SELECT COUNT(*) FROM info.news_articles
                    WHERE category = $1 AND is_deleted = FALSE
                """
                return await conn.fetchval(query, category)

    def _row_to_entity(self, row: asyncpg.Record) -> NewsArticle:
        """DB row를 NewsArticle 엔티티로 변환."""
        keywords = tuple(row["keywords"]) if row["keywords"] else None

        return NewsArticle(
            id=row["id"],
            title=row["title"],
            url=row["url"],
            snippet=row["snippet"],
            source=row["source"],
            source_name=row["source_name"],
            published_at=row["published_at"].replace(tzinfo=timezone.utc),
            thumbnail_url=row["thumbnail_url"],
            category=row["category"],
            source_icon_url=row["source_icon_url"],
            video_url=row["video_url"],
            keywords=keywords,
            ai_tag=row["ai_tag"],
        )

    async def close(self) -> None:
        """리소스 정리."""
        await self._pool.close()
