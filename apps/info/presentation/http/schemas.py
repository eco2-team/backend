"""HTTP Response Schemas.

Pydantic 모델 기반 API 응답 스키마.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class NewsArticleSchema(BaseModel):
    """뉴스 기사 스키마."""

    id: str = Field(..., description="기사 고유 ID")
    title: str = Field(..., description="기사 제목")
    url: str = Field(..., description="기사 원문 URL")
    snippet: str = Field(..., description="기사 요약")
    source: str = Field(..., description="뉴스 소스 (naver, newsdata)")
    source_name: str = Field(..., description="언론사 이름")
    published_at: str = Field(..., description="게시 시간 (ISO 8601)")
    thumbnail_url: str | None = Field(None, description="썸네일 이미지 URL")
    category: str | None = Field(None, description="카테고리")
    source_icon_url: str | None = Field(None, description="언론사 아이콘 URL")
    video_url: str | None = Field(None, description="동영상 URL")
    keywords: list[str] | None = Field(None, description="관련 키워드")
    ai_tag: str | None = Field(None, description="AI 기반 세부 태그")


class NewsMetaSchema(BaseModel):
    """뉴스 메타 정보 스키마."""

    total_cached: int = Field(..., description="캐시된 기사 총 수")
    cache_expires_in: int = Field(..., description="캐시 만료까지 남은 시간 (초)")


class NewsListResponseSchema(BaseModel):
    """뉴스 목록 응답 스키마."""

    articles: list[NewsArticleSchema] = Field(..., description="뉴스 기사 목록")
    next_cursor: str | None = Field(None, description="다음 페이지 커서")
    has_more: bool = Field(..., description="추가 데이터 존재 여부")
    meta: NewsMetaSchema = Field(..., description="메타 정보")


class CategorySchema(BaseModel):
    """카테고리 스키마."""

    id: str = Field(..., description="카테고리 ID")
    name: str = Field(..., description="카테고리 이름 (한국어)")


class CategoryListResponseSchema(BaseModel):
    """카테고리 목록 응답 스키마."""

    categories: list[CategorySchema] = Field(..., description="카테고리 목록")


class HealthCheckResponseSchema(BaseModel):
    """헬스체크 응답 스키마."""

    status: str = Field(..., description="서비스 상태")
    service: str = Field(..., description="서비스 이름")
