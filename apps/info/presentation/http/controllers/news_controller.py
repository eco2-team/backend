"""News Controller.

뉴스 API 엔드포인트 핸들러.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, HTTPException

from info.application.commands.fetch_news_command import FetchNewsCommand
from info.application.dto.news_request import NewsListRequest
from info.domain.constants import VALID_CATEGORIES, VALID_SOURCES
from info.presentation.http.schemas import (
    NewsListResponseSchema,
    NewsArticleSchema,
    NewsMetaSchema,
    CategoryListResponseSchema,
    CategorySchema,
)
from info.setup.dependencies import get_fetch_news_command

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/news", tags=["news"])


@router.get(
    "",
    response_model=NewsListResponseSchema,
    summary="뉴스 목록 조회",
    description="환경/에너지/AI 관련 뉴스를 무한스크롤 형태로 조회합니다.",
)
async def get_news(
    category: Annotated[
        str,
        Query(description="카테고리 (all, environment, energy, ai)"),
    ] = "all",
    cursor: Annotated[
        str | None,
        Query(description="페이지네이션 커서 (이전 응답의 next_cursor)"),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=50, description="조회할 기사 수"),
    ] = 10,
    source: Annotated[
        str,
        Query(description="뉴스 소스 (all, naver, newsdata)"),
    ] = "all",
    has_image: Annotated[
        bool,
        Query(description="이미지가 있는 기사만 반환 (Perplexity UI용)"),
    ] = False,
    command: FetchNewsCommand = Depends(get_fetch_news_command),
) -> NewsListResponseSchema:
    """뉴스 목록 조회.

    Cursor 기반 무한스크롤 페이지네이션을 지원합니다.

    - **category**: 카테고리 필터 (기본: all)
    - **cursor**: 이전 응답의 next_cursor 값 (첫 요청 시 생략)
    - **limit**: 한 번에 조회할 기사 수 (기본: 10, 최대: 50)
    - **source**: 뉴스 소스 필터 (기본: all)
    """
    # 카테고리 검증
    if category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Must be one of: {VALID_CATEGORIES}",
        )

    # 소스 검증
    if source not in VALID_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source. Must be one of: {VALID_SOURCES}",
        )

    # cursor 변환
    cursor_int = None
    if cursor:
        try:
            cursor_int = int(cursor)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid cursor format. Must be a numeric timestamp.",
            )

    # Command 실행
    request = NewsListRequest(
        category=category,
        cursor=cursor_int,
        limit=limit,
        source=source,
        has_image=has_image,
    )

    result = await command.execute(request)

    # Response Schema 생성 (타입 안전)
    return NewsListResponseSchema(
        articles=[
            NewsArticleSchema(
                id=a.id,
                title=a.title,
                url=a.url,
                snippet=a.snippet,
                source=a.source,
                source_name=a.source_name,
                published_at=a.published_at,
                thumbnail_url=a.thumbnail_url,
                category=a.category,
                source_icon_url=a.source_icon_url,
                video_url=a.video_url,
                keywords=a.keywords,
                ai_tag=a.ai_tag,
            )
            for a in result.articles
        ],
        next_cursor=result.next_cursor,
        has_more=result.has_more,
        meta=NewsMetaSchema(
            total_cached=result.meta.total_cached,
            cache_expires_in=result.meta.cache_expires_in,
        ),
    )


@router.get(
    "/categories",
    response_model=CategoryListResponseSchema,
    summary="카테고리 목록 조회",
    description="지원되는 뉴스 카테고리 목록을 조회합니다.",
)
async def get_categories() -> CategoryListResponseSchema:
    """카테고리 목록 조회."""
    categories = [
        CategorySchema(id="all", name="전체"),
        CategorySchema(id="environment", name="환경"),
        CategorySchema(id="energy", name="에너지"),
        CategorySchema(id="ai", name="AI"),
    ]

    return CategoryListResponseSchema(categories=categories)
