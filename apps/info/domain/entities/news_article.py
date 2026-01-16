"""News Article Entity."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime


@dataclass(frozen=True)
class NewsArticle:
    """뉴스 기사 엔티티.

    Attributes:
        id: 고유 식별자 (source_externalId 형식)
        title: 기사 제목
        url: 기사 원문 URL
        snippet: 기사 요약/발췌
        source: 뉴스 소스 ("naver" | "newsdata")
        source_name: 언론사 이름
        published_at: 게시 시간
        thumbnail_url: 썸네일 이미지 URL (optional)
        category: 카테고리 ("environment" | "energy" | "ai")
        source_icon_url: 언론사 아이콘 URL (optional)
        video_url: 동영상 URL (optional)
        keywords: 관련 키워드 목록 (optional)
        ai_tag: AI 기반 세부 태그 (optional)
    """

    id: str
    title: str
    url: str
    snippet: str
    source: str
    source_name: str
    published_at: datetime
    thumbnail_url: str | None = None
    category: str | None = None
    source_icon_url: str | None = None
    video_url: str | None = None
    keywords: tuple[str, ...] | None = None
    ai_tag: str | None = None

    @property
    def published_at_ms(self) -> int:
        """게시 시간을 밀리초 타임스탬프로 반환."""
        return int(self.published_at.timestamp() * 1000)

    def with_category(self, category: str) -> NewsArticle:
        """카테고리가 설정된 새 인스턴스 반환."""
        return replace(self, category=category)
