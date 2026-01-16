"""Postgres News Repository.

PostgreSQL을 사용한 뉴스 저장소 구현.
psycopg2를 사용하여 gevent 호환 동기 I/O 지원.
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
    from psycopg2.pool import ThreadedConnectionPool

logger = logging.getLogger(__name__)


class PostgresNewsRepository(NewsRepositoryPort):
    """PostgreSQL 뉴스 저장소.

    psycopg2를 사용하여 gevent 호환 동기 I/O 지원.
    UPSERT로 중복 처리, 커서 기반 페이지네이션 지원.
    """

    def __init__(self, pool: ThreadedConnectionPool):
        """초기화.

        Args:
            pool: psycopg2 ThreadedConnectionPool
        """
        self._pool = pool

    def upsert_articles(self, articles: list[NewsArticle]) -> int:
        """기사 일괄 저장 (UPSERT).

        INSERT ... ON CONFLICT (url) DO UPDATE로 중복 처리.
        """
        if not articles:
            return 0

        # UPSERT 쿼리 - psycopg2 스타일 (%s placeholder)
        query = """
            INSERT INTO info.news_articles (
                id, url, title, snippet,
                source, source_name, source_icon_url,
                thumbnail_url, video_url,
                category, keywords, ai_tag,
                published_at, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
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

        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                # executemany로 배치 처리
                values = [
                    (
                        a.id,
                        a.url,
                        a.title,
                        a.snippet,
                        a.source,
                        a.source_name,
                        a.source_icon_url,
                        a.thumbnail_url,
                        a.video_url,
                        a.category or "all",
                        list(a.keywords) if a.keywords else None,
                        a.ai_tag,
                        a.published_at,
                    )
                    for a in articles
                ]
                cur.executemany(query, values)
                count = cur.rowcount
                conn.commit()

                logger.info(
                    "Upserted news articles",
                    extra={"count": count, "total": len(articles)},
                )

                return count
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    def get_articles(
        self,
        category: str,
        cursor: NewsCursor | None = None,
        limit: int = 20,
    ) -> PaginatedResult:
        """카테고리별 기사 조회 (커서 기반 페이지네이션)."""
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                if cursor is None:
                    # 첫 페이지 (커서 없음)
                    if category == "all":
                        query = """
                            SELECT * FROM info.news_articles
                            WHERE is_deleted = FALSE
                            ORDER BY published_at DESC, id DESC
                            LIMIT %s
                        """
                        cur.execute(query, (limit + 1,))
                    else:
                        query = """
                            SELECT * FROM info.news_articles
                            WHERE category = %s AND is_deleted = FALSE
                            ORDER BY published_at DESC, id DESC
                            LIMIT %s
                        """
                        cur.execute(query, (category, limit + 1))
                else:
                    # 다음 페이지 (커서 사용)
                    if category == "all":
                        query = """
                            SELECT * FROM info.news_articles
                            WHERE is_deleted = FALSE
                              AND (published_at, id) < (%s, %s)
                            ORDER BY published_at DESC, id DESC
                            LIMIT %s
                        """
                        cur.execute(query, (cursor.published_at, cursor.article_id, limit + 1))
                    else:
                        query = """
                            SELECT * FROM info.news_articles
                            WHERE category = %s AND is_deleted = FALSE
                              AND (published_at, id) < (%s, %s)
                            ORDER BY published_at DESC, id DESC
                            LIMIT %s
                        """
                        cur.execute(
                            query, (category, cursor.published_at, cursor.article_id, limit + 1)
                        )

                # Fetch with column names
                columns = [desc[0] for desc in cur.description]
                rows = [dict(zip(columns, row)) for row in cur.fetchall()]

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

                # 총 개수 (첫 페이지에서만 조회)
                total_count = -1
                if cursor is None:
                    total_count = self.get_total_count(category)

                return PaginatedResult(
                    articles=articles,
                    next_cursor=next_cursor,
                    has_more=has_more,
                    total_count=total_count,
                )
        finally:
            self._pool.putconn(conn)

    def get_recent_articles(
        self,
        category: str,
        limit: int = 200,
    ) -> list[NewsArticle]:
        """최근 기사 조회 (캐시 워밍용)."""
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                if category == "all":
                    query = """
                        SELECT * FROM info.news_articles
                        WHERE is_deleted = FALSE
                        ORDER BY published_at DESC
                        LIMIT %s
                    """
                    cur.execute(query, (limit,))
                else:
                    query = """
                        SELECT * FROM info.news_articles
                        WHERE category = %s AND is_deleted = FALSE
                        ORDER BY published_at DESC
                        LIMIT %s
                    """
                    cur.execute(query, (category, limit))

                columns = [desc[0] for desc in cur.description]
                rows = [dict(zip(columns, row)) for row in cur.fetchall()]

                return [self._row_to_entity(row) for row in rows]
        finally:
            self._pool.putconn(conn)

    def get_total_count(self, category: str) -> int:
        """카테고리별 기사 총 개수."""
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                if category == "all":
                    query = """
                        SELECT COUNT(*) FROM info.news_articles
                        WHERE is_deleted = FALSE
                    """
                    cur.execute(query)
                else:
                    query = """
                        SELECT COUNT(*) FROM info.news_articles
                        WHERE category = %s AND is_deleted = FALSE
                    """
                    cur.execute(query, (category,))
                return cur.fetchone()[0]
        finally:
            self._pool.putconn(conn)

    def _row_to_entity(self, row: dict) -> NewsArticle:
        """DB row를 NewsArticle 엔티티로 변환."""
        keywords = tuple(row["keywords"]) if row["keywords"] else None

        published_at = row["published_at"]
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)

        return NewsArticle(
            id=row["id"],
            title=row["title"],
            url=row["url"],
            snippet=row["snippet"],
            source=row["source"],
            source_name=row["source_name"],
            published_at=published_at,
            thumbnail_url=row["thumbnail_url"],
            category=row["category"],
            source_icon_url=row["source_icon_url"],
            video_url=row["video_url"],
            keywords=keywords,
            ai_tag=row["ai_tag"],
        )

    def close(self) -> None:
        """리소스 정리."""
        self._pool.closeall()
