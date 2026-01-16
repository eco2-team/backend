"""Postgres News Repository (Read-Only).

PostgreSQL을 사용한 뉴스 저장소 읽기 구현.
Info API는 읽기만 담당 - Postgres Fallback용.
"""

from __future__ import annotations

import logging
from datetime import timezone
from typing import TYPE_CHECKING

from info.application.ports.news_repository import (
    NewsCursor,
    NewsRepositoryPort,
    PaginatedResult,
)
from info.domain.entities import NewsArticle

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)


class PostgresNewsRepository(NewsRepositoryPort):
    """PostgreSQL 뉴스 저장소 (읽기 전용).

    asyncpg를 사용하여 비동기 I/O 지원.
    Postgres Fallback용 - Redis 캐시 미스 시 사용.
    """

    def __init__(self, pool: asyncpg.Pool):
        """초기화.

        Args:
            pool: asyncpg connection pool
        """
        self._pool = pool

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

            # 총 개수 (첫 페이지에서만 조회, 성능 최적화)
            total_count = -1
            if cursor is None:
                total_count = await self.get_total_count(category)

            return PaginatedResult(
                articles=articles,
                next_cursor=next_cursor,
                has_more=has_more,
                total_count=total_count,
                source="postgres",
            )

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
