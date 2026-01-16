"""News Repository Port.

Postgres 뉴스 저장소 추상화 인터페이스.
Source of Truth로서 영구 저장 및 커서 기반 페이지네이션 지원.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from info_worker.domain.entities import NewsArticle


@dataclass(frozen=True)
class NewsCursor:
    """커서 기반 페이지네이션 커서.

    형식: {published_at_ms}_{article_id}
    """

    published_at: datetime
    article_id: str

    def encode(self) -> str:
        """커서 인코딩."""
        ts_ms = int(self.published_at.timestamp() * 1000)
        return f"{ts_ms}_{self.article_id}"

    @classmethod
    def decode(cls, cursor: str) -> NewsCursor:
        """커서 디코딩."""
        ts_str, article_id = cursor.rsplit("_", 1)
        from datetime import timezone

        published_at = datetime.fromtimestamp(int(ts_str) / 1000, tz=timezone.utc)
        return cls(published_at=published_at, article_id=article_id)


@dataclass(frozen=True)
class PaginatedResult:
    """페이지네이션 결과."""

    articles: list[NewsArticle]
    next_cursor: NewsCursor | None
    has_more: bool
    total_count: int


class NewsRepositoryPort(ABC):
    """뉴스 저장소 포트 (Postgres).

    영구 저장소로서 UPSERT 및 커서 기반 페이지네이션 지원.
    psycopg2 동기 드라이버 사용 (gevent 몽키패칭 호환).
    """

    @abstractmethod
    def upsert_articles(self, articles: list[NewsArticle]) -> int:
        """기사 일괄 저장 (UPSERT).

        URL 기반 중복 제거. 기존 기사는 updated_at만 갱신.

        Args:
            articles: 저장할 기사 목록

        Returns:
            저장/갱신된 기사 수
        """
        pass

    @abstractmethod
    def get_articles(
        self,
        category: str,
        cursor: NewsCursor | None = None,
        limit: int = 20,
    ) -> PaginatedResult:
        """카테고리별 기사 조회 (커서 기반 페이지네이션).

        Args:
            category: 카테고리 ("all", "environment", "energy", "ai")
            cursor: 페이지네이션 커서 (None이면 최신부터)
            limit: 조회할 기사 수

        Returns:
            페이지네이션 결과
        """
        pass

    @abstractmethod
    def get_recent_articles(
        self,
        category: str,
        limit: int = 200,
    ) -> list[NewsArticle]:
        """최근 기사 조회 (캐시 워밍용).

        Args:
            category: 카테고리
            limit: 조회할 기사 수

        Returns:
            최근 기사 목록 (시간순 내림차순)
        """
        pass

    @abstractmethod
    def get_total_count(self, category: str) -> int:
        """카테고리별 기사 총 개수.

        Args:
            category: 카테고리

        Returns:
            기사 개수
        """
        pass

    def close(self) -> None:
        """리소스 정리 (optional)."""
        pass
