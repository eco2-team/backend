"""News Response DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from info.domain.entities import NewsArticle


@dataclass
class NewsArticleResponse:
    """뉴스 기사 응답 DTO."""

    id: str
    title: str
    url: str
    snippet: str
    source: str
    source_name: str
    published_at: str  # ISO 8601
    thumbnail_url: str | None
    category: str | None
    source_icon_url: str | None
    video_url: str | None
    keywords: list[str] | None
    ai_tag: str | None

    @classmethod
    def from_entity(cls, article: NewsArticle) -> NewsArticleResponse:
        """Entity에서 DTO로 변환."""
        return cls(
            id=article.id,
            title=article.title,
            url=article.url,
            snippet=article.snippet,
            source=article.source,
            source_name=article.source_name,
            published_at=article.published_at.isoformat(),
            thumbnail_url=article.thumbnail_url,
            category=article.category,
            source_icon_url=article.source_icon_url,
            video_url=article.video_url,
            keywords=list(article.keywords) if article.keywords else None,
            ai_tag=article.ai_tag,
        )


@dataclass
class NewsMeta:
    """뉴스 메타 정보."""

    total_cached: int
    cache_expires_in: int  # 초
    source: str = "redis"  # "redis" or "postgres"


@dataclass
class NewsListResponse:
    """뉴스 목록 응답 DTO."""

    articles: list[NewsArticleResponse]
    next_cursor: str | None
    has_more: bool
    meta: NewsMeta
