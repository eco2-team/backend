"""News Repository Port (Read-Only).

Postgres 뉴스 저장소 읽기 인터페이스.
Info API는 읽기만 담당하고, 쓰기는 info_worker가 담당.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from info.domain.entities import NewsArticle


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
        published_at = datetime.fromtimestamp(int(ts_str) / 1000, tz=timezone.utc)
        return cls(published_at=published_at, article_id=article_id)


@dataclass(frozen=True)
class PaginatedResult:
    """페이지네이션 결과."""

    articles: list[NewsArticle]
    next_cursor: NewsCursor | None
    has_more: bool
    total_count: int
    source: str  # "redis" or "postgres"


class NewsRepositoryPort(ABC):
    """뉴스 저장소 포트 (읽기 전용).

    Postgres fallback용 읽기 인터페이스.
    """

    @abstractmethod
    async def get_articles(
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
    async def get_total_count(self, category: str) -> int:
        """카테고리별 기사 총 개수.

        Args:
            category: 카테고리

        Returns:
            기사 개수
        """
        pass

    async def close(self) -> None:
        """리소스 정리 (optional)."""
        pass
