"""News Request DTOs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NewsListRequest:
    """뉴스 목록 요청 DTO."""

    category: str = "all"
    cursor: int | None = None
    limit: int = 10
    source: str = "all"  # "all", "naver", "newsdata"
    has_image: bool = False  # True이면 이미지 있는 기사만 반환
